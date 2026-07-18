import datetime
import re
import uuid

from bson import ObjectId
from flask import current_app, jsonify, request, session

from backend.extensions import mongo
from backend.lexinit.api.validation import GENERATION_FIELD_MESSAGES, parse_json_model
from backend.lexinit.schemas import GenerationRequest, GenerationV1Request
from backend.lexinit.services.learner_context import learner_context_snapshot
from backend.routes.sources import source_service
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

        rate_limit_response = ensure_generation_quota(user_id, user_doc, mode=mode)
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

        rate_limit_response = ensure_generation_quota(user_id, user_doc, mode=mode)
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
        rate_limit_response = ensure_generation_quota(
            session["user_id"], user_doc, mode=retry_mode
        )
        if rate_limit_response:
            return rate_limit_response
        job = retry_generation_job(
            current_app._get_current_object(), job_id, session["user_id"]
        )
        if not job:
            # Retry was rejected; return the quota slot consumed above.
            counter = "deep_rate_limit" if retry_mode == DEEP_FOCUS_MODE else "rate_limit"
            mongo.db.users.update_one(
                {"_id": ObjectId(session["user_id"]), counter: {"$gt": 0}},
                {"$inc": {counter: -1}},
            )
            return jsonify(
                {
                    "success": False,
                    "message": "This generation run cannot be retried.",
                }
            ), 409
        return jsonify({"success": True, **job}), 202


# Generations allowed per 24-hour window, by plan. None means unlimited.
PLAN_GENERATION_LIMITS = {
    "free": 5,
    "plus": 20,
    "pro": None,
}

# Deep Focus (Pro Reasoning) generations allowed per 24-hour window, by plan.
# Deep Focus has its own separate budget and does NOT consume the quick
# (Basic) generation limit. None means unlimited.
PLAN_DEEP_FOCUS_LIMITS = {
    "free": 3,
    "plus": None,
    "pro": None,
}

DEEP_FOCUS_MODE = "Pro Reasoning"


def _plan_limit(user_doc, config_key, defaults):
    plan = str(user_doc.get("plan") or "free").strip().lower()
    limits = current_app.config.get(config_key) or defaults
    if plan in limits:
        return limits[plan]
    return limits.get("free")


def generation_limit_for(user_doc):
    return _plan_limit(user_doc, "PLAN_GENERATION_LIMITS", PLAN_GENERATION_LIMITS)


def deep_focus_limit_for(user_doc):
    return _plan_limit(user_doc, "PLAN_DEEP_FOCUS_LIMITS", PLAN_DEEP_FOCUS_LIMITS)


def ensure_generation_quota(user_id, user_doc, mode=None):
    """Atomically consume one generation from the user's 24-hour quota.

    Deep Focus (Pro Reasoning) generations additionally consume a
    deep-focus slot, which has its own per-plan limit. Counters are
    incremented here (before generation starts) with conditional updates,
    so concurrent requests cannot exceed the limits. On terminal
    generation failure the charge is refunded once
    (see backend.services.generation_jobs.refund_generation_quota).
    """
    is_deep = mode == DEEP_FOCUS_MODE
    limit = deep_focus_limit_for(user_doc) if is_deep else generation_limit_for(user_doc)
    if limit is None:
        return None  # unlimited for this mode on this plan

    now = datetime.datetime.now(datetime.timezone.utc)
    window = datetime.timedelta(hours=24)
    first_time = user_doc.get("first_submission_time")
    if first_time and first_time.tzinfo is None:
        first_time = first_time.replace(tzinfo=datetime.timezone.utc)

    counter = "deep_rate_limit" if is_deep else "rate_limit"

    if not first_time or now - first_time >= window:
        # New window: reset both budgets and consume the first slot.
        mongo.db.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "first_submission_time": now,
                    "rate_limit": 0 if is_deep else 1,
                    "deep_rate_limit": 1 if is_deep else 0,
                }
            },
        )
        return None

    # Within the window: consume a slot only if this mode's limit allows it.
    result = mongo.db.users.update_one(
        {"_id": ObjectId(user_id), counter: {"$lt": limit}},
        {"$inc": {counter: 1}},
    )
    if result.modified_count == 0:
        remaining = window - (now - first_time)
        hours = remaining.seconds // 3600
        minutes = (remaining.seconds % 3600) // 60
        if is_deep:
            message = (
                f"Deep Focus limit reached ({limit} per 24 hours). "
                f"Try Quick mode, or try Deep Focus again in {hours}h {minutes}m."
            )
        else:
            message = f"Rate limit exceeded. Try again in {hours}h {minutes}m."
        return jsonify({"success": False, "message": message}), 429
    return None


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
