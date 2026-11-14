from bson import ObjectId
from flask import jsonify, request, session

from backend.extensions import mongo
from backend.lexinit.api.errors import ApiError
from backend.lexinit.services.course_progress import CourseProgressService
from backend.session_store import get_user_session, list_user_sessions
from backend.validation import valid_safe_id


def _user_id():
    value = session.get("user_id")
    if not value:
        raise ApiError("User not logged in.", status_code=401, code="authentication_required")
    try:
        return ObjectId(value)
    except Exception as exc:
        session.clear()
        raise ApiError("User not logged in.", status_code=401, code="authentication_required") from exc


def _owned_session(user_id, session_id):
    if not valid_safe_id(session_id):
        raise ApiError("Invalid course link.", code="invalid_session_id")
    session_data = get_user_session(user_id, session_id)
    if not session_data:
        raise ApiError("Course not found.", status_code=404, code="session_not_found")
    return session_data


def _course_with_goal(user_id, session_data):
    from backend.lexinit.services.learner_model import course_goal_plan

    course = CourseProgressService(mongo.db).course(user_id, session_data)
    course["goal"] = course_goal_plan(mongo.db, user_id, session_data["_id"], course)
    return course


def _transfer_mastery(user_id, session_data):
    """Carry over what the learner already knows from other courses (once)."""
    if session_data.get("mastery_transfer_checked"):
        return
    try:
        from backend.lexinit.repositories import MongoAdaptiveLearningRepository
        from backend.lexinit.services.learner_model import transfer_prior_mastery

        transfer_prior_mastery(
            mongo.db,
            MongoAdaptiveLearningRepository(
                evidence_collection=mongo.db.mastery_evidence,
                mastery_collection=mongo.db.concept_mastery,
                decisions_collection=mongo.db.adaptation_decisions,
            ),
            user_id,
            session_data,
        )
    except Exception:
        from flask import current_app

        current_app.logger.warning("mastery_transfer_failed", exc_info=True)


def _final_service():
    from backend.lexinit.repositories import MongoAdaptiveLearningRepository
    from backend.lexinit.services import AdaptiveLearningService
    from backend.lexinit.services.final_assessment import FinalAssessmentService
    from backend.clients import get_gemini_model
    from backend.routes.coach import _coach_model

    return FinalAssessmentService(
        db=mongo.db,
        # The final decides the badge, so it uses the main model rather than
        # the faster coach model.
        generator=get_gemini_model(),
        verifier=_coach_model(),
        adaptive_service=AdaptiveLearningService(
            MongoAdaptiveLearningRepository(
                evidence_collection=mongo.db.mastery_evidence,
                mastery_collection=mongo.db.concept_mastery,
                decisions_collection=mongo.db.adaptation_decisions,
            )
        ),
        course_progress=CourseProgressService(mongo.db),
    )


def register_routes(app):
    @app.route("/api/v1/sessions/<session_id>/final-assessment")
    def final_assessment_status(session_id):
        user_id = _user_id()
        return jsonify(
            _final_service().status(user_id=user_id, session_data=_owned_session(user_id, session_id))
        )

    @app.route("/api/v1/sessions/<session_id>/final-assessment", methods=["POST"])
    def start_final_assessment(session_id):
        user_id = _user_id()
        return jsonify(
            _final_service().start(user_id=user_id, session_data=_owned_session(user_id, session_id))
        )

    @app.route("/api/v1/final-assessments/<final_id>")
    def get_final_assessment(final_id):
        return jsonify(_final_service().get(user_id=_user_id(), final_id=final_id))

    @app.route("/api/v1/final-assessments/<final_id>/submit", methods=["POST"])
    def submit_final_assessment(final_id):
        user_id = _user_id()
        data = request.get_json(silent=True) or {}
        return jsonify(
            _final_service().submit(
                user_id=user_id,
                final_id=final_id,
                answers=data.get("answers"),
                session_data_loader=lambda session_id: get_user_session(user_id, str(session_id)),
            )
        )

    @app.route("/api/v1/courses")
    def courses():
        user_id = _user_id()
        sessions = list_user_sessions(user_id, limit=12)
        return jsonify({"courses": CourseProgressService(mongo.db).summaries(user_id, sessions)})

    @app.route("/api/v1/sessions/<session_id>/course")
    def course(session_id):
        user_id = _user_id()
        session_data = _owned_session(user_id, session_id)
        _transfer_mastery(user_id, session_data)
        return jsonify(_course_with_goal(user_id, session_data))

    @app.route("/api/v1/sessions/<session_id>/goal", methods=["PUT"])
    def set_goal(session_id):
        from backend.lexinit.services.learner_model import parse_goal_date, set_course_goal

        user_id = _user_id()
        session_data = _owned_session(user_id, session_id)
        data = request.get_json(silent=True) or {}
        try:
            target = parse_goal_date(data.get("target_date"))
        except ValueError as exc:
            raise ApiError(
                "Choose a date from today up to one year ahead.", code="invalid_goal_date"
            ) from exc
        set_course_goal(mongo.db, user_id, session_data["_id"], target)
        return jsonify(_course_with_goal(user_id, session_data))

    @app.route("/api/v1/sessions/<session_id>/course/activities/<activity_id>", methods=["PUT"])
    def update_course_activity(session_id, activity_id):
        user_id = _user_id()
        data = request.get_json(silent=True) or {}
        try:
            result = CourseProgressService(mongo.db).set_activity_status(
                user_id, _owned_session(user_id, session_id), activity_id, data.get("status")
            )
        except ValueError as exc:
            raise ApiError(str(exc), code="invalid_course_activity") from exc
        return jsonify(result)

    @app.route("/api/v1/sessions/<session_id>/course/modules/<module_id>/unlock", methods=["POST"])
    def unlock_course_module(session_id, module_id):
        user_id = _user_id()
        try:
            result = CourseProgressService(mongo.db).unlock_module(
                user_id, _owned_session(user_id, session_id), module_id
            )
        except ValueError as exc:
            raise ApiError(str(exc), code="invalid_course_module") from exc
        return jsonify(result)
