from typing import Literal

from bson import ObjectId
from flask import current_app, jsonify, request, session
from pydantic import BaseModel, ConfigDict, Field

from backend.clients import get_gemini_model
from backend.extensions import mongo
from backend.lexinit.api.errors import ApiError
from backend.lexinit.api.validation import parse_json_model
from backend.lexinit.repositories import MongoAdaptiveLearningRepository
from backend.lexinit.services.concept_coach import ConceptCoachService
from backend.validation import valid_safe_id


class FixItRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: str = Field(min_length=24, max_length=24)
    question_index: int = Field(ge=0, le=50)


class ExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=8, max_length=64)
    concept_id: str = Field(min_length=3, max_length=160)
    style: Literal["simpler", "analogy", "example", "step_by_step"] = "simpler"


class ExplanationFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    helpful: bool


class PracticeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(min_length=8, max_length=64)
    concept_id: str = Field(min_length=3, max_length=160)


class QuestionReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["assessment", "final", "check"]
    reference_id: str = Field(min_length=8, max_length=80)
    question_index: int = Field(default=0, ge=0, le=60)
    reason: Literal["wrong_answer", "unclear", "off_topic", "other"]
    note: str = Field(default="", max_length=500)


class CheckAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: int = Field(ge=0, le=9)


def _user_id() -> str:
    user_id = session.get("user_id")
    try:
        return str(ObjectId(user_id))
    except Exception as exc:
        session.clear()
        raise ApiError("User not logged in.", status_code=401, code="authentication_required") from exc


def coach_service() -> ConceptCoachService:
    return ConceptCoachService(
        db=mongo.db,
        generator=_coach_model(),
        adaptive_repository=MongoAdaptiveLearningRepository(
            evidence_collection=mongo.db.mastery_evidence,
            mastery_collection=mongo.db.concept_mastery,
            decisions_collection=mongo.db.adaptation_decisions,
        ),
    )


def _coach_model():
    """A fast model keeps in-course help near-instant; the main model is the
    fallback when no coach model is configured or it is unavailable."""
    coach_model = (current_app.config.get("GEMINI_COACH_MODEL_NAME") or "").strip()
    main_model = current_app.config.get("GEMINI_MODEL_NAME")
    if not coach_model or coach_model == main_model:
        return get_gemini_model()
    return get_gemini_model(coach_model, [main_model] if main_model else [])


def booster_service():
    from backend.lexinit.services.booster import BoosterService

    # The lesson is written by the main model; answer keys are checked by the
    # faster coach model.
    return BoosterService(
        coach=coach_service(),
        generator=get_gemini_model(),
        verifier=_coach_model(),
    )


def _safe_session_id(value: str) -> str:
    if not valid_safe_id(value):
        raise ApiError("Invalid course link.", code="invalid_session_id")
    return value


def register_routes(app):
    @app.route("/api/v1/coach/fix-it", methods=["POST"])
    def coach_fix_it():
        user_id = _user_id()
        payload = parse_json_model(FixItRequest, request.get_json(silent=True))
        return jsonify(
            coach_service().fix_it(
                user_id=user_id,
                submission_id=payload.submission_id,
                question_index=payload.question_index,
            )
        )

    @app.route("/api/v1/coach/explain", methods=["POST"])
    def coach_explain():
        user_id = _user_id()
        payload = parse_json_model(ExplainRequest, request.get_json(silent=True))
        return jsonify(
            coach_service().explain(
                user_id=user_id,
                session_id=_safe_session_id(payload.session_id),
                concept_id=payload.concept_id,
                style=payload.style,
            )
        )

    @app.route("/api/v1/coach/explanations/<explanation_id>/feedback", methods=["POST"])
    def coach_explanation_feedback(explanation_id):
        user_id = _user_id()
        payload = parse_json_model(ExplanationFeedbackRequest, request.get_json(silent=True))
        return jsonify(
            coach_service().explanation_feedback(
                user_id=user_id,
                explanation_id=explanation_id,
                helpful=payload.helpful,
            )
        )

    @app.route("/api/v1/coach/preferences")
    def coach_preferences():
        return jsonify(coach_service().preferences(user_id=_user_id()))

    @app.route("/api/v1/coach/practice", methods=["POST"])
    def coach_practice():
        user_id = _user_id()
        payload = parse_json_model(PracticeRequest, request.get_json(silent=True))
        return jsonify(
            coach_service().practice(
                user_id=user_id,
                session_id=_safe_session_id(payload.session_id),
                concept_id=payload.concept_id,
            )
        )

    @app.route("/api/v1/coach/sessions/<session_id>/booster")
    def coach_booster_status(session_id):
        return jsonify(
            booster_service().status(user_id=_user_id(), session_id=_safe_session_id(session_id))
        )

    @app.route("/api/v1/coach/sessions/<session_id>/booster", methods=["POST"])
    def coach_booster_create(session_id):
        return jsonify(
            booster_service().create(user_id=_user_id(), session_id=_safe_session_id(session_id))
        )

    @app.route("/api/v1/coach/sessions/<session_id>/mastery")
    def coach_course_mastery(session_id):
        return jsonify(
            coach_service().course_mastery(
                user_id=_user_id(), session_id=_safe_session_id(session_id)
            )
        )

    @app.route("/api/v1/coach/sessions/<session_id>/modules/<module_id>")
    def coach_module_overview(session_id, module_id):
        return jsonify(
            coach_service().module_overview(
                user_id=_user_id(),
                session_id=_safe_session_id(session_id),
                module_id=module_id,
            )
        )

    @app.route("/api/v1/coach/sessions/<session_id>/modules/<module_id>/pre-check", methods=["POST"])
    def coach_pre_check(session_id, module_id):
        return jsonify(
            coach_service().pre_check(
                user_id=_user_id(),
                session_id=_safe_session_id(session_id),
                module_id=module_id,
            )
        )

    @app.route("/api/v1/coach/daily-mix")
    def coach_daily_mix_status():
        return jsonify(coach_service().daily_mix_status(user_id=_user_id()))

    @app.route("/api/v1/coach/daily-mix", methods=["POST"])
    def coach_daily_mix():
        return jsonify(coach_service().daily_mix(user_id=_user_id()))

    @app.route("/api/v1/question-reports", methods=["POST"])
    def create_question_report():
        from backend.lexinit.services.question_quality import report_question

        user_id = _user_id()
        payload = parse_json_model(QuestionReportRequest, request.get_json(silent=True))
        return jsonify(
            report_question(
                mongo.db,
                user_id=ObjectId(user_id),
                source=payload.source,
                reference_id=payload.reference_id,
                question_index=payload.question_index,
                reason=payload.reason,
                note=payload.note,
            )
        ), 201

    @app.route("/api/v1/coach/checks/<check_id>/answer", methods=["POST"])
    def coach_answer_check(check_id):
        user_id = _user_id()
        payload = parse_json_model(CheckAnswerRequest, request.get_json(silent=True))
        return jsonify(
            coach_service().answer_check(
                user_id=user_id,
                check_id=check_id,
                answer=payload.answer,
            )
        )
