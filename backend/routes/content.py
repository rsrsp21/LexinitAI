import re
import uuid

from bson import ObjectId
from flask import current_app, jsonify, request, session

from backend.extensions import mongo
from backend.lexinit.api.validation import GENERATION_FIELD_MESSAGES, parse_json_model
from backend.lexinit.schemas import GenerationRequest, GenerationV1Request
from backend.lexinit.services.learner_context import learner_context_snapshot
from backend.routes.sources import source_service
from backend.services.generation_quota import (
    consume_generation_quota,
    release_quota_charge,
)
from backend.services.generation_jobs import (
    cancel_generation_job,
    enqueue_generation_job,
    get_active_generation_jobs,
    get_generation_job,
    retry_generation_job,
)
from backend.services.content_generation import canonicalize_topic, clean_topic_text
from backend.session_store import find_cached_session, get_user_session, normalize_topic
from backend.validation import valid_safe_id


def register_routes(app):
    @app.route("/api/v1/generation-runs", methods=["POST"])
    @app.route("/submit-topic", methods=["POST"])
    def submit_topic():
        if "user_id" not in session:
            return jsonify({"success": False, "message": "User not logged in."}), 401

        user_id = session["user_id"]
        request_contract = GenerationV1Request if request.path.startswith("/api/v1/") else GenerationRequest
        generation_request = parse_json_model(
            request_contract,
            request.get_json(silent=True),
            field_messages=GENERATION_FIELD_MESSAGES,
        )

        raw_topic = generation_request.topic
        original_topic = clean_topic_text(raw_topic)
        grounding = source_service().grounding_bundle(
            user_id=user_id,
            source_ids=generation_request.source_ids,
            query=original_topic,
        )
        topic = canonicalize_topic(original_topic)
        difflvl = generation_request.difflevel.value
        mode = generation_request.mode.value

        adaptive_source = None
        adaptive_submission_id = generation_request.assessment_submission_id
        if adaptive_submission_id is not None:
            if not valid_safe_id(adaptive_submission_id):
                return jsonify({"success": False, "message": "Invalid assessment submission id."}), 400
            try:
                submission_lookup_id = ObjectId(adaptive_submission_id)
            except Exception:
                return jsonify({"success": False, "message": "Invalid assessment submission id."}), 400
            assessment_submission = mongo.db.assessment_submissions.find_one(
                {"_id": submission_lookup_id, "user_id": ObjectId(user_id)}
            )
            if not assessment_submission:
                return jsonify({"success": False, "message": "Assessment submission not found."}), 404
            weak_topic = (assessment_submission.get("weak_topic") or "").strip()
            if not weak_topic or normalize_topic(weak_topic) != normalize_topic(original_topic):
                return jsonify({"success": False, "message": "Adaptive topic does not match this assessment."}), 400
            adaptive_source = {
                "assessment_submission_id": assessment_submission["_id"],
                "session_id": assessment_submission.get("session_id"),
                "topic": assessment_submission.get("source_topic") or "Untitled course",
            }

        user_doc = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        if not user_doc:
            return jsonify({"success": False, "message": "User not found."}), 404
        personalization_profile = learner_context_snapshot(user_doc)

        cached_session = (
            None
            if adaptive_source or grounding
            else find_cached_session(
                user_id,
                topic,
                difflvl,
                mode,
                personalization_profile=personalization_profile,
            )
        )
        if cached_session:
            return jsonify(
                {
                    "success": True,
                    "cached": True,
                    "message": "Using cached generated session.",
                    "user_id": user_id,
                    "session_id": str(cached_session["_id"]),
                    "difficulty_level": cached_session.get("difficulty_level"),
                    "topic": cached_session.get("topic"),
                }
            )

        rate_limit_response, quota_charge = consume_generation_quota(user_id, user_doc, mode=mode)
        if rate_limit_response:
            return rate_limit_response

        job = enqueue_generation_job(
            current_app._get_current_object(),
            user_id,
            topic,
            difflvl,
            mode,
            original_topic=original_topic,
            force_new=bool(adaptive_source),
            adaptive_source=adaptive_source,
            source_grounding=grounding,
            idempotency_key=generation_idempotency_key(),
            quota_charge=quota_charge,
        )
        return generation_started_response(job)

    @app.route("/api/v1/sessions/<session_id>/regenerate", methods=["POST"])
    @app.route("/api/sessions/<session_id>/regenerate", methods=["POST"])
    def regenerate_session(session_id):
        if "user_id" not in session:
            return jsonify({"success": False, "message": "User not logged in."}), 401

        if not valid_safe_id(session_id):
            return jsonify({"success": False, "message": "Invalid course link."}), 400
        user_id = session["user_id"]
        user_doc = mongo.db.users.find_one({"_id": ObjectId(user_id)})
        if not user_doc:
            return jsonify({"success": False, "message": "User not found."}), 404

        source_session = get_user_session(user_id, session_id)
        if not source_session:
            return jsonify({"success": False, "message": "Course not found."}), 404

        topic = (source_session.get("topic") or "").strip()
        difflvl = (source_session.get("difficulty_level") or "").strip().lower()
        mode = source_session.get("generation_mode") or source_session.get("mode") or "Basic"
        if not topic or not difflvl:
            return jsonify({"success": False, "message": "This session is missing topic or difficulty details."}), 400

        rate_limit_response, quota_charge = consume_generation_quota(user_id, user_doc, mode=mode)
        if rate_limit_response:
            return rate_limit_response

        next_version = next_session_version(user_id, topic, difflvl, mode)
        source_ids = [str(item) for item in source_session.get("source_ids") or []]
        grounding = source_service().grounding_bundle(
            user_id=user_id,
            source_ids=source_ids,
            query=topic,
        )
        job = enqueue_generation_job(
            current_app._get_current_object(),
            user_id,
            topic,
            difflvl,
            mode,
            force_new=True,
            regenerated_from=str(source_session["_id"]),
            version=next_version,
            source_grounding=grounding,
            idempotency_key=generation_idempotency_key(),
            quota_charge=quota_charge,
        )
        job["message"] = (
            job["message"] if job.get("deduplicated") else f"Creating version {next_version}."
        )
        return generation_started_response(job)

    @app.route("/api/v1/generation-runs/active")
    @app.route("/api/generation-jobs/active")
    def active_generation_jobs():
        if "user_id" not in session:
            return jsonify({"message": "User not logged in."}), 401
        return jsonify({"runs": get_active_generation_jobs(session["user_id"])})

    @app.route("/api/v1/generation-runs/<job_id>")
    @app.route("/api/generation-jobs/<job_id>")
    def generation_job(job_id):
        if "user_id" not in session:
            return jsonify({"message": "User not logged in."}), 401

        if not isinstance(job_id, str) or not re.fullmatch(r"[a-f0-9]{32}", job_id):
            return jsonify({"message": "Invalid generation job id."}), 400
        job = get_generation_job(job_id, session["user_id"])
        if not job:
            return jsonify({"message": "Generation job not found."}), 404

        return jsonify(job)

    @app.route("/api/v1/generation-runs/<job_id>/cancel", methods=["POST"])
    @app.route("/api/generation-jobs/<job_id>/cancel", methods=["POST"])
    def cancel_generation(job_id):
        if "user_id" not in session:
            return jsonify({"message": "User not logged in."}), 401
        if not valid_generation_job_id(job_id):
            return jsonify({"message": "Invalid generation job id."}), 400
        job = cancel_generation_job(job_id, session["user_id"])
        if not job:
            return jsonify({"message": "Generation job not found."}), 404
        return jsonify({"success": True, **job})

    @app.route("/api/v1/generation-runs/<job_id>/retry", methods=["POST"])
    @app.route("/api/generation-jobs/<job_id>/retry", methods=["POST"])
    def retry_generation(job_id):
        if "user_id" not in session:
            return jsonify({"message": "User not logged in."}), 401
        if not valid_generation_job_id(job_id):
            return jsonify({"message": "Invalid generation job id."}), 400
        existing = get_generation_job(job_id, session["user_id"])
        if not existing:
            return jsonify({"message": "Generation job not found."}), 404
        user_doc = mongo.db.users.find_one({"_id": ObjectId(session["user_id"])})
        if not user_doc:
            return jsonify({"message": "User not found."}), 404
        retry_mode = existing.get("mode") or "Basic"
        rate_limit_response, quota_charge = consume_generation_quota(
            session["user_id"], user_doc, mode=retry_mode
        )
        if rate_limit_response:
            return rate_limit_response
        job = retry_generation_job(
            current_app._get_current_object(),
            job_id,
            session["user_id"],
            quota_charge=quota_charge,
        )
        if not job:
            # Retry was rejected; return the quota slot consumed above.
            release_quota_charge(session["user_id"], quota_charge)
            return jsonify(
                {
                    "success": False,
                    "message": "This generation run cannot be retried.",
                }
            ), 409
        return jsonify({"success": True, **job}), 202


def generation_idempotency_key():
    value = (request.headers.get("Idempotency-Key") or "").strip()
    if not value:
        return uuid.uuid4().hex
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", value):
        from backend.lexinit.api.errors import ApiError

        raise ApiError(
            "Invalid idempotency key.",
            code="invalid_idempotency_key",
            details={"header": "Idempotency-Key"},
        )
    return value


def generation_started_response(job):
    status_code = 200 if job.get("status") == "completed" else 202
    return jsonify(
        {
            "success": True,
            "queued": job.get("status") in {"queued", "running", "repairing", "saving"},
            "job_id": job["id"],
            **job,
        }
    ), status_code


def valid_generation_job_id(job_id):
    return isinstance(job_id, str) and bool(re.fullmatch(r"[a-f0-9]{32}", job_id))


def next_session_version(user_id, topic, difflvl, mode):
    existing_count = mongo.db.sessions.count_documents(
        {
            "user_id": ObjectId(user_id),
            "normalized_topic": normalize_topic(topic),
            "difficulty_level": (difflvl or "").strip().lower(),
            "generation_mode": mode or "Basic",
        }
    )
    return existing_count + 1
