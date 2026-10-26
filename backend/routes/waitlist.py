import datetime

from flask import jsonify, request

from backend.extensions import mongo
from backend.lexinit.api.errors import ApiError
from backend.routes.auth import _clean_text, _normalize_email, _validate_email

WAITLIST_GOALS = {"exam", "career", "curiosity", "teaching"}


def register_routes(app):
    @app.route("/api/v1/waitlist", methods=["POST"])
    def join_waitlist():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            data = {}

        email = _normalize_email(data.get("email"))
        error = _validate_email(email)
        if error:
            raise ApiError(error, code="invalid_email")

        name = _clean_text(data.get("name"))
        if len(name) > 80:
            raise ApiError("Name must be 80 characters or fewer.", code="invalid_name")

        goal = _clean_text(data.get("goal"))
        if goal and goal not in WAITLIST_GOALS:
            raise ApiError("Choose a valid learning goal.", code="invalid_goal")

        now = datetime.datetime.now(datetime.timezone.utc)
        updates = {"updated_at": now}
        if name:
            updates["name"] = name
        if goal:
            updates["goal"] = goal
        mongo.db.waitlist.update_one(
            {"email": email},
            {"$set": updates, "$setOnInsert": {"email": email, "created_at": now}},
            upsert=True,
        )
        # Same response for new and repeat signups so the endpoint can't be
        # used to check whether an address is already on the list.
        return jsonify({"success": True, "message": "You are on the list."}), 201
