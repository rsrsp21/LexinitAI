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


def register_routes(app):
    @app.route("/api/v1/courses")
    def courses():
        user_id = _user_id()
        sessions = list_user_sessions(user_id, limit=12)
        return jsonify({"courses": CourseProgressService(mongo.db).summaries(user_id, sessions)})

    @app.route("/api/v1/sessions/<session_id>/course")
    def course(session_id):
        user_id = _user_id()
        return jsonify(CourseProgressService(mongo.db).course(user_id, _owned_session(user_id, session_id)))

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
