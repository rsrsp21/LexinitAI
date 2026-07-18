import re

from bson import ObjectId
from flask import current_app, jsonify, request, session

from backend.extensions import mongo
from backend.lexinit.api.errors import ApiError
from backend.lexinit.api.validation import parse_json_model
from backend.lexinit.domain.assessment import AssessmentIntegrityError, AssessmentSubmissionError
from backend.lexinit.repositories import MongoAdaptiveLearningRepository, MongoAssessmentSubmissionRepository
from backend.lexinit.schemas import (
    AttemptAnswerRequest,
    FinalizeAssessmentAttemptRequest,
    StartAssessmentAttemptRequest,
)
from backend.lexinit.services import AdaptiveLearningService, AssessmentSubmissionService
from backend.lexinit.services.assessment_attempts import AdaptiveAssessmentAttemptService
from backend.routes.activity import _analyze_weak_topic
from backend.session_store import get_user_session
from backend.validation import valid_safe_id


def _authenticated_user_id() -> ObjectId:
    user_id = session.get("user_id")
    try:
        return ObjectId(user_id)
    except Exception as exc:
        session.clear()
        raise ApiError(
            "User not logged in.",
            status_code=401,
            code="authentication_required",
        ) from exc


def _idempotency_key() -> str:
    value = (request.headers.get("Idempotency-Key") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", value):
        raise ApiError(
            "A valid Idempotency-Key header is required.",
            code="invalid_idempotency_key",
            details={"header": "Idempotency-Key"},
        )
    return value


def _attempt_service() -> AdaptiveAssessmentAttemptService:
    secret = current_app.config.get("SECRET_KEY")
    if not secret:
        raise ApiError(
            "Assessment attempts are temporarily unavailable.",
            status_code=503,
            code="attempt_service_unavailable",
        )
    return AdaptiveAssessmentAttemptService(
        attempts_collection=mongo.db.assessment_attempts,
        question_bank_collection=mongo.db.assessment_question_bank,
        mastery_collection=mongo.db.concept_mastery,
        secret_key=str(secret),
    )


def _adaptive_service() -> AdaptiveLearningService:
    repository = MongoAdaptiveLearningRepository(
        evidence_collection=mongo.db.mastery_evidence,
        mastery_collection=mongo.db.concept_mastery,
        decisions_collection=mongo.db.adaptation_decisions,
    )
    return AdaptiveLearningService(repository)


def register_routes(app):
    @app.route("/api/v1/sessions/<session_id>/assessment-submissions")
    def list_session_assessment_submissions(session_id):
        user_id = _authenticated_user_id()
        if not valid_safe_id(session_id):
            raise ApiError("Invalid course link.", code="invalid_session_id")
        session_data = get_user_session(str(user_id), session_id)
        if not session_data:
            raise ApiError("Course not found.", status_code=404, code="session_not_found")

        session_ids = [session_data["_id"]]
        if session_id != str(session_data["_id"]):
            session_ids.append(session_id)
        submissions = []
        for item in (
            mongo.db.assessment_submissions.find(
                {"user_id": user_id, "session_id": {"$in": session_ids}},
                {
                    "session_id": 1,
                    "source_topic": 1,
                    "assessment_type": 1,
                    "score": 1,
                    "total": 1,
                    "weak_topic": 1,
                    "created_at": 1,
                },
            )
            .sort("created_at", -1)
            .limit(100)
        ):
            total = max(0, int(item.get("total") or 0))
            score = max(0, int(item.get("score") or 0))
            created_at = item.get("created_at")
            submissions.append(
                {
                    "submission_id": str(item["_id"]),
                    "session_id": str(item.get("session_id") or session_id),
                    "topic": str(item.get("source_topic") or session_data.get("topic") or "Untitled course"),
                    "assessment_type": str(item.get("assessment_type") or "assessment"),
                    "score": score,
                    "total": total,
                    "percentage": round(score / total * 100, 1) if total else 0,
                    "weak_topic": str(item.get("weak_topic") or ""),
                    "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else None,
                }
            )
        return jsonify({"assessments": submissions})

    @app.route("/api/v1/assessment-submissions/<submission_id>")
    def get_assessment_submission(submission_id):
        user_id = _authenticated_user_id()
        try:
            object_id = ObjectId(submission_id)
        except Exception as exc:
            raise ApiError(
                "Invalid assessment result.",
                code="invalid_assessment_submission_id",
            ) from exc
        submission = mongo.db.assessment_submissions.find_one(
            {"_id": object_id, "user_id": user_id}
        )
        if not submission:
            raise ApiError(
                "Assessment result not found.",
                status_code=404,
                code="assessment_submission_not_found",
            )

        questions = submission.get("questions") or []
        feedback = submission.get("feedback") or []
        question_results = []
        for index, question in enumerate(questions):
            item_feedback = feedback[index] if index < len(feedback) else {}
            question_results.append(
                {
                    "question": str(question.get("question") or f"Question {index + 1}"),
                    "selected_answer": question.get("selected_answer"),
                    "selected_option": question.get("selected_option"),
                    "options": question.get("options") or [],
                    "correct": bool(item_feedback.get("correct")),
                    "correct_answer": item_feedback.get("correct_answer"),
                    "explanation": str(item_feedback.get("explanation") or ""),
                }
            )

        total = max(0, int(submission.get("total") or 0))
        score = max(0, int(submission.get("score") or 0))
        created_at = submission.get("created_at")
        return jsonify(
            {
                "submission_id": str(submission["_id"]),
                "session_id": str(submission.get("session_id") or ""),
                "source_topic": str(submission.get("source_topic") or "Untitled course"),
                "assessment_type": str(submission.get("assessment_type") or "mcq"),
                "score": score,
                "total": total,
                "percentage": round(score / total * 100, 1) if total else 0,
                "weak_topic": str(submission.get("weak_topic") or ""),
                "module_id": submission.get("module_id"),
                "attempt_id": submission.get("attempt_id"),
                "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else None,
                "questions": question_results,
            }
        )

    @app.route("/api/v1/sessions/<session_id>/assessment-attempts", methods=["POST"])
    def start_assessment_attempt(session_id):
        user_id = _authenticated_user_id()
        if not valid_safe_id(session_id):
            raise ApiError("Invalid course link.", code="invalid_session_id")
        payload = parse_json_model(
            StartAssessmentAttemptRequest,
            request.get_json(silent=True),
            field_messages={
                "assessment_type": "Invalid assessment type.",
                "question_count": "Question count must be between 1 and 10.",
            },
        )
        session_data = get_user_session(str(user_id), session_id)
        if not session_data:
            raise ApiError("Course not found.", status_code=404, code="session_not_found")
        attempt = _attempt_service().start(
            user_id=user_id,
            requested_session_id=session_id,
            session_data=session_data,
            assessment_type=payload.assessment_type,
            question_count=payload.question_count,
            module_id=payload.module_id,
            idempotency_key=_idempotency_key(),
        )
        return jsonify(attempt), 201

    @app.route("/api/v1/assessment-attempts/<attempt_id>")
    def get_assessment_attempt(attempt_id):
        return jsonify(
            _attempt_service().get(
                attempt_id=attempt_id,
                user_id=_authenticated_user_id(),
            )
        )

    @app.route("/api/v1/assessment-attempts/<attempt_id>/answers", methods=["POST"])
    def answer_assessment_attempt(attempt_id):
        payload = parse_json_model(
            AttemptAnswerRequest,
            request.get_json(silent=True),
            field_messages={
                "question_id": "Invalid assigned question.",
                "answer": "An answer is required.",
            },
        )
        result = _attempt_service().answer(
            attempt_id=attempt_id,
            user_id=_authenticated_user_id(),
            question_id=payload.question_id,
            answer=payload.answer,
            idempotency_key=_idempotency_key(),
        )
        return jsonify(result)

    @app.route("/api/v1/assessment-attempts/<attempt_id>/submit", methods=["POST"])
    def finalize_assessment_attempt(attempt_id):
        user_id = _authenticated_user_id()
        payload = parse_json_model(
            FinalizeAssessmentAttemptRequest,
            request.get_json(silent=True),
            field_messages={"submission_token": "Invalid assessment submission token."},
        )
        attempt_service = _attempt_service()
        locked, questions, answers = attempt_service.begin_finalization(
            attempt_id=attempt_id,
            user_id=user_id,
            submission_token=payload.submission_token,
            idempotency_key=_idempotency_key(),
        )
        if locked.get("status") == "completed" and locked.get("public_result"):
            return jsonify(locked["public_result"])

        session_data = get_user_session(str(user_id), str(locked["session_id"]))
        if not session_data:
            attempt_service.reset_finalization(locked["_id"])
            raise ApiError("Course not found.", status_code=404, code="session_not_found")
        service = AssessmentSubmissionService(
            MongoAssessmentSubmissionRepository(mongo.db.assessment_submissions),
            _analyze_weak_topic,
            adaptive_learning_service=_adaptive_service(),
        )
        try:
            outcome = service.submit(
                user_id=user_id,
                requested_session_id=str(locked["session_id"]),
                session_data=session_data,
                assessment_type=payload_assessment_type(locked),
                answers=answers,
                questions_override=questions,
                attempt_id=str(locked["_id"]),
            )
        except AssessmentSubmissionError as exc:
            attempt_service.reset_finalization(locked["_id"])
            raise ApiError(str(exc), code="invalid_assessment_submission") from exc
        except AssessmentIntegrityError as exc:
            attempt_service.reset_finalization(locked["_id"])
            current_app.logger.error(
                "assessment_attempt_integrity_error attempt_id=%s error=%s",
                attempt_id,
                exc,
            )
            raise ApiError(
                "This assessment is unavailable because its stored questions are invalid.",
                status_code=500,
                code="assessment_integrity_error",
            ) from exc
        except Exception:
            attempt_service.reset_finalization(locked["_id"])
            raise

        response = outcome.public_response()
        attempt_service.complete_finalization(locked["_id"], response)
        return jsonify(response)


def payload_assessment_type(attempt):
    from backend.lexinit.schemas import AssessmentType

    return AssessmentType(attempt["assessment_type"])
