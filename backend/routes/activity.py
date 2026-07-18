from bson import ObjectId
import math
import re

from flask import current_app, jsonify, request, session
from youtube_transcript_api import NoTranscriptFound, TranscriptsDisabled, VideoUnavailable, YouTubeTranscriptApi

from backend.clients import get_gemini_model, get_youtube_client_with_credentials
from backend.extensions import mongo
from backend.lexinit.api.errors import ApiError
from backend.lexinit.api.validation import parse_json_model
from backend.lexinit.domain.assessment import AssessmentIntegrityError, AssessmentSubmissionError
from backend.lexinit.repositories import MongoAdaptiveLearningRepository, MongoAssessmentSubmissionRepository
from backend.lexinit.schemas import AssessmentSubmissionRequest, AssessmentType
from backend.lexinit.schemas.adaptive import WeakTopicAnalysis
from backend.lexinit.services import AdaptiveLearningService, AssessmentSubmissionService
from backend.session_store import get_user_session, session_lookup_id
from backend.validation import clean_string, valid_safe_id, valid_video_id


def _analyze_weak_topic(incorrect_explanations):
    query = (
        f"{incorrect_explanations}\n"
        "This is an API call for analyzing mistakes in assessments. "
        "I attempted the above questions incorrectly, and the explanations provided are for the correct answers. "
        "Infer the main weak topic and 1 to 3 related subtopics that need focused remediation. "
        "Use concise educational topic names and do not invent unrelated weaknesses."
    )
    analysis = get_gemini_model().generate_structured(
        query,
        WeakTopicAnalysis,
        temperature=0.1,
    )
    return f"{analysis.main_topic}: {', '.join(analysis.related_subtopics)}"


def _build_adaptive_learning_service():
    repository = MongoAdaptiveLearningRepository(
        evidence_collection=mongo.db.mastery_evidence,
        mastery_collection=mongo.db.concept_mastery,
        decisions_collection=mongo.db.adaptation_decisions,
    )
    return AdaptiveLearningService(repository)


def register_routes(app):
    @app.route("/save-score", methods=["POST"])
    def save_score():
        return jsonify({"success": False, "message": "Client-supplied scores are no longer accepted."}), 410

    @app.route("/api/v1/sessions/<session_id>/assessments/<question_type>/submit", methods=["POST"])
    @app.route("/api/sessions/<session_id>/assessments/<question_type>/submit", methods=["POST"])
    def submit_assessment(session_id, question_type):
        user_id = session.get("user_id")
        if not user_id:
            raise ApiError(
                "User not logged in.",
                status_code=401,
                code="authentication_required",
            )
        if not valid_safe_id(session_id):
            raise ApiError("Invalid course link.", code="invalid_session_id")

        try:
            assessment_type = AssessmentType(question_type)
        except ValueError as exc:
            raise ApiError("Invalid assessment type.", code="invalid_assessment_type") from exc

        submission_request = parse_json_model(
            AssessmentSubmissionRequest,
            request.get_json(silent=True),
            field_messages={"answers": "Answers must be provided as a list."},
        )
        session_data = get_user_session(user_id, session_id)
        if not session_data:
            raise ApiError("Course not found.", status_code=404, code="session_not_found")

        try:
            user_object_id = ObjectId(user_id)
        except Exception as exc:
            session.clear()
            raise ApiError(
                "User not logged in.",
                status_code=401,
                code="authentication_required",
            ) from exc

        repository = MongoAssessmentSubmissionRepository(mongo.db.assessment_submissions)
        service = AssessmentSubmissionService(
            repository,
            _analyze_weak_topic,
            adaptive_learning_service=_build_adaptive_learning_service(),
        )
        questions_override = None
        if submission_request.module_id:
            modules = (session_data.get("curriculum") or {}).get("modules", [])
            if submission_request.module_id not in {
                str(module.get("module_id")) for module in modules if module.get("module_id")
            }:
                raise ApiError("Invalid course module.", code="invalid_course_module")
            from backend.lexinit.domain.assessment import questions_for_assessment

            module_order = [
                str(module.get("module_id")) for module in modules if module.get("module_id")
            ]
            questions_override = [
                question
                for index, question in enumerate(
                    questions_for_assessment(session_data, assessment_type)
                )
                if question.get("module_id") == submission_request.module_id
                or (
                    not question.get("module_id")
                    and module_order
                    and module_order[index % len(module_order)]
                    == submission_request.module_id
                )
            ]
            if not questions_override:
                raise ApiError(
                    "This module has no assessment questions.",
                    code="assessment_empty",
                )
        try:
            outcome = service.submit(
                user_id=user_object_id,
                requested_session_id=session_id,
                session_data=session_data,
                assessment_type=assessment_type,
                answers=submission_request.answers,
                questions_override=questions_override,
            )
        except AssessmentSubmissionError as exc:
            raise ApiError(str(exc), code="invalid_assessment_submission") from exc
        except AssessmentIntegrityError as exc:
            current_app.logger.error(
                "assessment_integrity_error session_id=%s type=%s error=%s",
                session_id,
                assessment_type.value,
                exc,
            )
            raise ApiError(
                "This assessment is unavailable because its stored questions are invalid.",
                status_code=500,
                code="assessment_integrity_error",
            ) from exc

        return jsonify(outcome.public_response())

    @app.route("/summarize", methods=["POST"])
    def summarize():
        if "user_id" not in session:
            return jsonify({"error": "User not logged in."}), 401
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "A JSON request body is required."}), 400
        video_id = data.get("videoId")
        if not valid_video_id(video_id):
            return jsonify({"error": "Invalid YouTube video id."}), 400

        try:
            youtube = get_youtube_client_with_credentials()
            video_response = youtube.videos().list(part="snippet", id=video_id).execute()

            if not video_response.get("items"):
                return jsonify({"summary": "Video not found."}), 404

            video = video_response["items"][0]
            title = video["snippet"]["title"]
            description = video["snippet"]["description"]

            try:
                transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
                transcript = transcripts.find_transcript(["en"])
                transcript_text = " ".join([item.text for item in transcript.fetch()])
            except TranscriptsDisabled:
                return jsonify({"summary": "Transcripts are disabled for this video."}), 404
            except NoTranscriptFound:
                return jsonify({"summary": "Transcript not found for this video."}), 404
            except VideoUnavailable:
                return jsonify({"summary": "The video is unavailable."}), 404
            except Exception as exc:
                print("Transcript error:", str(exc))
                return jsonify({"summary": "Error fetching transcript."}), 404

            query = f"""
Summarize the following video content in a clear and structured manner:

Title: {title}
Description: {description}
Transcript: {transcript_text}

- Highlight key points concisely.
- Use bullet points or tables for clarity.
- Keep it direct. Strictly avoid introductions like "Here is the summary.", any intros and conclusion phrases.
- Maintain accuracy while removing unnecessary details.
"""
            response = get_gemini_model().generate_content(query)
            summary = response.text.strip() if hasattr(response, "text") else str(response)
            return jsonify({"summary": summary})
        except Exception as exc:
            print("Unexpected error:", str(exc))
            return jsonify({"error": str(exc)}), 500
    @app.route("/save-watchtime", methods=["POST"])
    def save_watchtime():
        try:
            user_id = session.get("user_id")
            if not user_id:
                return jsonify({"success": False, "message": "User not logged in."}), 401
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify({"success": False, "message": "Invalid data received"}), 400

            session_id = data.get("session_id")
            video_id = data.get("videoId")
            watch_time = data.get("watchTime")

            if not valid_safe_id(session_id) or not valid_video_id(video_id):
                return jsonify({"success": False, "message": "Invalid course or video link."}), 400
            if isinstance(watch_time, bool) or not isinstance(watch_time, (int, float)) or not math.isfinite(watch_time):
                return jsonify({"success": False, "message": "Watch time must be a number."}), 400
            if watch_time < 0 or watch_time > 86400:
                return jsonify({"success": False, "message": "Watch time is outside the allowed range."}), 400
            if not session_id or not video_id or watch_time is None:
                return jsonify({"success": False, "message": "Missing required fields"}), 400

            result = mongo.db.sessions.update_one(
                {
                    "_id": {"$in": session_lookup_id(session_id)},
                    "user_id": ObjectId(user_id),
                },
                {
                    "$set": {
                        "course_content.$[contentElem].watch_time": watch_time,
                    }
                },
                array_filters=[
                    {"contentElem.link": {"$regex": f"v={re.escape(video_id)}($|&)"}},
                ],
            )

            if result.modified_count == 0:
                return jsonify({"success": False, "message": "Video Lecture not found in this course."}), 404

            return jsonify({"success": True, "message": "Time submitted successfully!"}), 200
        except Exception as exc:
            print("Error:", str(exc))
            return jsonify({"success": False, "message": str(exc)}), 500

    @app.route("/improve-score", methods=["POST"])
    def improve_score():
        try:
            if "user_id" not in session:
                return jsonify({"error": "User not logged in."}), 401
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify({"error": "A JSON request body is required."}), 400
            incorrect_explanations = clean_string(
                data.get("incorrectExplanations"), min_length=10, max_length=12_000
            )

            if not incorrect_explanations:
                return jsonify({"error": "Incorrect-answer context must be between 10 and 12000 characters."}), 400

            topic = _analyze_weak_topic(incorrect_explanations)
            return jsonify({"topic": topic})
        except Exception as exc:
            print(f"Error: {str(exc)}")
            return jsonify({"error": str(exc)}), 500
