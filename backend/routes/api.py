import datetime

from bson import ObjectId
from flask import jsonify, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from backend.extensions import mongo
from backend.lexinit.api.validation import parse_json_model
from backend.lexinit.schemas.profile import ProfileType, ProfileUpdateRequest
from backend.session_store import delete_user_session, get_user_session, list_user_sessions
from backend.validation import clean_string, valid_safe_id, validate_password


ASSESSMENT_FIELDS = {
    "mcqs",
    "mcq",
    "mcq_questions",
    "true_false",
    "truefalse",
    "true_false_questions",
    "oneword",
    "one_word",
    "oneword_questions",
    "one_word_questions",
}


def _serialize(value):
    if isinstance(value, ObjectId):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def _public_session(session_data):
    """Return session content without pre-submission assessment solutions."""
    public = dict(session_data)
    for field in ASSESSMENT_FIELDS:
        questions = public.get(field)
        if not isinstance(questions, list):
            continue
        public[field] = [
            {key: value for key, value in question.items() if key not in {"answer", "correct_answer", "explanation"}}
            if isinstance(question, dict)
            else question
            for question in questions
        ]
    return _serialize(public)


def _current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    try:
        object_id = ObjectId(user_id)
    except Exception:
        session.clear()
        return None
    return mongo.db.users.find_one({"_id": object_id})


def _public_user(user):
    user_id = str(user["_id"])
    return {
        "_id": user_id,
        "name": user.get("name"),
        "email": user.get("email"),
        "profile_type": user.get("profile_type", ProfileType.INDEPENDENT.value),
        "institution_name": user.get("institution_name"),
        "grade_or_class": user.get("grade_or_class"),
        "organization_name": user.get("organization_name"),
        "professional_role": user.get("professional_role"),
        "work_experience_years": user.get("work_experience_years"),
        "profile_complete": user.get("profile_complete", True),
        "plan": user.get("plan", "free"),
        "rate_limit": user.get("rate_limit", 0),
        "deep_rate_limit": user.get("deep_rate_limit", 0),
        "first_submission_time": _serialize(user.get("first_submission_time")),
    }


def register_routes(app):
    @app.route("/api/v1/me")
    @app.route("/api/me")
    def api_me():
        user = _current_user()
        if not user:
            return jsonify({"authenticated": False}), 401
        return jsonify({"authenticated": True, "user": _public_user(user)})

    @app.route("/api/v1/me/profile", methods=["PATCH"])
    @app.route("/api/me/profile", methods=["PATCH"])
    def api_update_profile():
        user = _current_user()
        if not user:
            return jsonify({"message": "User not logged in."}), 401

        payload = parse_json_model(
            ProfileUpdateRequest,
            request.get_json(silent=True),
            field_messages={
                "": "Complete the required details for the selected profile type.",
                "name": "Name must be between 2 and 80 characters.",
                "profile_type": "Choose student, professional, or independent learner.",
                "institution_name": "School or college name must be 120 characters or fewer.",
                "grade_or_class": "Grade or class must be 80 characters or fewer.",
                "organization_name": "Organization name must be 120 characters or fewer.",
                "professional_role": "Role or job title must be 120 characters or fewer.",
                "work_experience_years": "Work experience must be between 0 and 70 years.",
            },
        )

        profile_type = payload.profile_type.value
        values = {
            "name": payload.name,
            "profile_type": profile_type,
            "profile_updated_at": datetime.datetime.now(datetime.timezone.utc),
            "profile_complete": True,
        }
        unset = {}
        if payload.profile_type == ProfileType.STUDENT:
            values.update(
                institution_name=payload.institution_name,
                grade_or_class=payload.grade_or_class,
            )
            unset = {
                "organization_name": "",
                "professional_role": "",
                "work_experience_years": "",
            }
        elif payload.profile_type == ProfileType.PROFESSIONAL:
            values.update(
                organization_name=payload.organization_name,
                professional_role=payload.professional_role,
                work_experience_years=payload.work_experience_years,
            )
            unset = {"institution_name": "", "grade_or_class": ""}
        else:
            unset = {
                "institution_name": "",
                "grade_or_class": "",
                "organization_name": "",
                "professional_role": "",
                "work_experience_years": "",
            }

        mongo.db.users.update_one(
            {"_id": user["_id"]},
            {"$set": values, "$unset": unset},
        )
        updated_user = mongo.db.users.find_one({"_id": user["_id"]})
        return jsonify(
            {
                "success": True,
                "message": "Profile updated successfully.",
                "user": _public_user(updated_user),
            }
        )

    @app.route("/api/v1/sessions")
    @app.route("/api/sessions")
    def api_sessions():
        user = _current_user()
        if not user:
            return jsonify({"message": "User not logged in."}), 401

        query = clean_string(request.args.get("q", ""), max_length=100)
        if query is None:
            return jsonify({"message": "Search query must be 100 characters or fewer."}), 400
        sessions = list_user_sessions(str(user["_id"]), limit=50, query=query)
        return jsonify({"sessions": [_public_session(item) for item in sessions]})

    @app.route("/api/v1/sessions/<session_id>")
    @app.route("/api/sessions/<session_id>")
    def api_session(session_id):
        user = _current_user()
        if not user:
            return jsonify({"message": "User not logged in."}), 401

        if not valid_safe_id(session_id):
            return jsonify({"message": "Invalid course link."}), 400
        user_sessions = list_user_sessions(str(user["_id"]), limit=30)
        session_data = get_user_session(user["_id"], session_id)
        if not session_data:
            return jsonify({"message": "Course not found."}), 404

        return jsonify(
            {
                "user": {
                    "_id": str(user["_id"]),
                    "name": user.get("name"),
                    "email": user.get("email"),
                },
                "session": _public_session(session_data),
                "sessions": [_public_session(item) for item in user_sessions],
            }
        )

    @app.route("/api/v1/sessions/<session_id>", methods=["DELETE"])
    @app.route("/api/sessions/<session_id>", methods=["DELETE"])
    def api_delete_session(session_id):
        user = _current_user()
        if not user:
            return jsonify({"message": "User not logged in."}), 401

        if not valid_safe_id(session_id):
            return jsonify({"message": "Invalid course link."}), 400
        session_data = get_user_session(user["_id"], session_id)
        if not session_data:
            return jsonify({"message": "Course not found."}), 404

        data = request.get_json(silent=True) or {}
        confirm_code = str(data.get("confirm_code") or "").strip()
        expected_code = str(session_data["_id"])[-6:]
        if confirm_code != expected_code:
            return jsonify({"message": "Confirmation code does not match."}), 400

        result = delete_user_session(user["_id"], session_id)
        if result.deleted_count != 1:
            return jsonify({"message": "Session could not be deleted."}), 500

        return jsonify({"success": True, "message": "Session deleted."})

    @app.route("/api/v1/logout", methods=["POST"])
    @app.route("/api/logout", methods=["POST"])
    def api_logout():
        session.clear()
        return jsonify({"success": True})

    @app.route("/api/v1/account/password", methods=["POST"])
    @app.route("/api/account/password", methods=["POST"])
    def api_change_password():
        user = _current_user()
        if not user:
            return jsonify({"message": "User not logged in."}), 401

        data = request.get_json(silent=True) or {}
        current_password = data.get("current_password")
        new_password = data.get("new_password")
        confirm_password = data.get("confirm_password")

        if not all(isinstance(value, str) and value for value in (current_password, new_password, confirm_password)):
            return jsonify({"message": "Please fill all password fields."}), 400
        if new_password != confirm_password:
            return jsonify({"message": "New passwords do not match."}), 400
        password_error = validate_password(new_password)
        if password_error:
            return jsonify({"message": password_error}), 400
        if len(current_password) > 128:
            return jsonify({"message": "Current password is invalid."}), 400
        if not check_password_hash(user["password"], current_password):
            return jsonify({"message": "Current password is incorrect."}), 400

        mongo.db.users.update_one(
            {"_id": user["_id"]},
            {
                "$set": {
                    "password": generate_password_hash(new_password),
                    "forgot_password": False,
                },
                "$unset": {
                    "temp_password": "",
                    "temp_password_created_at": "",
                    "temp_password_expires_at": "",
                },
            },
        )
        return jsonify({"success": True, "message": "Password updated successfully."})
