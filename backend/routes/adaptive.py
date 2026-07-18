from __future__ import annotations

from bson import ObjectId
import datetime
import re

from flask import current_app, jsonify, request, session

from backend.extensions import mongo
from backend.lexinit.api.errors import ApiError
from backend.lexinit.api.validation import parse_json_model
from backend.lexinit.repositories import MongoAdaptiveLearningRepository
from backend.lexinit.schemas import ReviewEventRequest
from backend.lexinit.schemas.adaptive import MasteryBand
from backend.lexinit.services.reviews import ReviewLearningService
from backend.lexinit.services.dashboard import build_learner_dashboard
from backend.session_store import get_user_session


def _build_adaptive_repository():
    return MongoAdaptiveLearningRepository(
        evidence_collection=mongo.db.mastery_evidence,
        mastery_collection=mongo.db.concept_mastery,
        decisions_collection=mongo.db.adaptation_decisions,
    )


def _authenticated_user_id() -> str:
    user_id = session.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        raise ApiError(
            "User not logged in.",
            status_code=401,
            code="authentication_required",
        )
    try:
        return str(ObjectId(user_id))
    except Exception as exc:
        session.clear()
        raise ApiError(
            "User not logged in.",
            status_code=401,
            code="authentication_required",
        ) from exc


def _limit() -> int:
    raw = request.args.get("limit", "100")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ApiError("Limit must be a number between 1 and 100.", code="invalid_limit") from exc
    if not 1 <= value <= 100:
        raise ApiError("Limit must be a number between 1 and 100.", code="invalid_limit")
    return value


def _serialize_mastery(items):
    return [item.public_dict() for item in items]


def _review_service():
    repository = _build_adaptive_repository()
    return ReviewLearningService(
        repository=repository,
        mastery_collection=mongo.db.concept_mastery,
        evidence_collection=mongo.db.mastery_evidence,
        decisions_collection=mongo.db.adaptation_decisions,
        review_events_collection=mongo.db.review_events,
        sessions_collection=mongo.db.sessions,
        question_bank_collection=mongo.db.assessment_question_bank,
    )


def _idempotency_key():
    value = (request.headers.get("Idempotency-Key") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", value):
        raise ApiError(
            "A valid Idempotency-Key header is required.",
            code="invalid_idempotency_key",
            details={"header": "Idempotency-Key"},
        )
    return value


def register_routes(app):
    @app.route("/api/v1/learners/me/dashboard")
    def learner_dashboard():
        return jsonify(build_learner_dashboard(mongo.db, _authenticated_user_id()))

    @app.route("/api/v1/learners/me/mastery")
    def learner_mastery():
        user_id = _authenticated_user_id()
        raw_band = request.args.get("band")
        bands = None
        if raw_band:
            try:
                bands = {MasteryBand(raw_band.strip().lower())}
            except ValueError as exc:
                raise ApiError(
                    "Band must be weak, developing, proficient, or mastered.",
                    code="invalid_mastery_band",
                ) from exc
        items = _build_adaptive_repository().list_mastery(
            user_id,
            bands=bands,
            limit=_limit(),
        )
        return jsonify({"mastery": _serialize_mastery(items)})

    @app.route("/api/v1/learners/me/weak-concepts")
    def learner_weak_concepts():
        user_id = _authenticated_user_id()
        items = _build_adaptive_repository().list_mastery(
            user_id,
            bands={MasteryBand.WEAK, MasteryBand.DEVELOPING},
            limit=_limit(),
        )
        return jsonify({"weak_concepts": _serialize_mastery(items)})

    @app.route("/api/v1/learners/me/reviews")
    def learner_reviews():
        user_id = _authenticated_user_id()
        raw_due_before = request.args.get("due_before")
        if raw_due_before:
            try:
                due_before = datetime.datetime.fromisoformat(
                    raw_due_before.replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise ApiError(
                    "due_before must be an ISO-8601 date-time.",
                    code="invalid_due_before",
                ) from exc
            if due_before.tzinfo is None:
                due_before = due_before.replace(tzinfo=datetime.timezone.utc)
        else:
            due_before = datetime.datetime.now(datetime.timezone.utc)
        reviews = _review_service().due_reviews(
            user_id=user_id,
            due_before=due_before,
            limit=_limit(),
        )
        return jsonify({"reviews": reviews, "due_count": len(reviews)})

    @app.route("/api/v1/learners/me/reviews", methods=["POST"])
    def record_learner_review():
        user_id = _authenticated_user_id()
        payload = parse_json_model(
            ReviewEventRequest,
            request.get_json(silent=True),
            field_messages={
                "concept_id": "Invalid review concept.",
                "rating": "Rating must be again, hard, good, or easy.",
                "artifact_id": "Invalid review artifact.",
                "session_id": "Invalid review session.",
            },
        )
        result = _review_service().record_review(
            user_id=user_id,
            concept_id=payload.concept_id,
            rating=payload.rating,
            idempotency_key=_idempotency_key(),
            artifact_id=payload.artifact_id,
            session_id=payload.session_id,
        )
        return jsonify({"success": True, **result})

    @app.route("/api/v1/learners/me/next-action")
    def learner_next_action():
        recommendation = _review_service().next_best_action(
            user_id=_authenticated_user_id()
        )
        return jsonify({"recommendation": recommendation})

    @app.route("/api/v1/adaptation-decisions/<decision_id>/generate", methods=["POST"])
    def generate_adaptive_decision(decision_id):
        user_id = _authenticated_user_id()
        user_object_id = ObjectId(user_id)
        decision = mongo.db.adaptation_decisions.find_one(
            {"_id": decision_id, "user_id": user_object_id}
        )
        if not decision:
            raise ApiError(
                "Adaptive recommendation not found.",
                status_code=404,
                code="adaptation_decision_not_found",
            )
        evidence_ids = list(decision.get("evidence_ids") or [])
        evidence = mongo.db.mastery_evidence.find_one(
            {"_id": {"$in": evidence_ids}, "user_id": user_object_id},
            sort=[("observed_at", -1)],
        )
        if not evidence:
            raise ApiError(
                "The recommendation has no usable learning evidence.",
                status_code=409,
                code="adaptation_evidence_missing",
            )
        source_session = get_user_session(user_id, str(evidence["session_id"]))
        if not source_session:
            raise ApiError(
                "The source course is unavailable.",
                status_code=409,
                code="source_session_missing",
            )
        mastery = mongo.db.concept_mastery.find_one(
            {"user_id": user_object_id, "concept_id": decision["concept_id"]}
        )
        if not mastery:
            raise ApiError(
                "The recommendation concept is unavailable.",
                status_code=409,
                code="mastery_not_found",
            )
        target_concept_ids = list(
            decision.get("target_concept_ids") or [decision["concept_id"]]
        )
        target_objective_ids = list(decision.get("target_objective_ids") or [])
        _validate_curriculum_targets(
            source_session,
            target_concept_ids=target_concept_ids,
            target_objective_ids=target_objective_ids,
        )

        from backend.routes.content import ensure_generation_quota, generation_started_response
        from backend.services.generation_jobs import enqueue_generation_job

        user_doc = mongo.db.users.find_one({"_id": user_object_id})
        if not user_doc:
            raise ApiError("User not found.", status_code=404, code="user_not_found")
        quota_response = ensure_generation_quota(
            user_id, user_doc, mode=source_session.get("generation_mode") or "Basic"
        )
        if quota_response:
            return quota_response
        concept_labels = _curriculum_concept_labels(source_session, target_concept_ids)
        focus = ", ".join(concept_labels) or str(mastery.get("concept_label") or "focused review")
        topic = f"{source_session.get('topic') or 'Learning'}: {focus}"[:500]
        target_difficulty = decision.get("target_difficulty") or "easy"
        target_difficulty = getattr(target_difficulty, "value", target_difficulty)
        adaptive_action = decision.get("action")
        adaptive_action = getattr(adaptive_action, "value", adaptive_action)
        job = enqueue_generation_job(
            current_app._get_current_object(),
            user_id,
            topic,
            str(target_difficulty),
            source_session.get("generation_mode") or "Basic",
            force_new=True,
            original_topic=topic,
            adaptive_source={
                "assessment_submission_id": decision.get("source_submission_id"),
                "session_id": source_session["_id"],
                "topic": source_session.get("topic") or "Untitled course",
                "decision_id": decision_id,
                "adaptive_action": adaptive_action,
                "target_concept_ids": target_concept_ids,
                "target_objective_ids": target_objective_ids,
            },
            idempotency_key=_idempotency_key(),
        )
        return generation_started_response(job)


def _validate_curriculum_targets(session_data, *, target_concept_ids, target_objective_ids):
    curriculum = session_data.get("curriculum") or {}
    modules = curriculum.get("modules") if isinstance(curriculum, dict) else []
    known_concepts = {
        item.get("concept_id")
        for module in modules or []
        for item in module.get("concepts", [])
        if isinstance(item, dict)
    }
    known_objectives = {
        item.get("objective_id")
        for module in modules or []
        for item in module.get("learning_objectives", [])
        if isinstance(item, dict)
    }
    if known_concepts and not set(target_concept_ids).issubset(known_concepts):
        raise ApiError(
            "The recommendation references an unknown Learning Path concept.",
            status_code=409,
            code="invalid_adaptation_target",
        )
    if known_objectives and not set(target_objective_ids).issubset(known_objectives):
        raise ApiError(
            "The recommendation references an unknown learning objective.",
            status_code=409,
            code="invalid_adaptation_target",
        )


def _curriculum_concept_labels(session_data, concept_ids):
    wanted = set(concept_ids)
    curriculum = session_data.get("curriculum") or {}
    modules = curriculum.get("modules") if isinstance(curriculum, dict) else []
    return [
        str(item.get("name"))
        for module in modules or []
        for item in module.get("concepts", [])
        if isinstance(item, dict) and item.get("concept_id") in wanted and item.get("name")
    ]
