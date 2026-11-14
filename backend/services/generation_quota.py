"""Per-plan daily generation quotas.

Each user has one 24-hour window that starts with their first charged
generation. Quick and Deep Focus generations have separate counters inside
that window. Every change is a conditional MongoDB update, so concurrent
requests can neither exceed a limit nor reset the window twice.

A charge records which counter it used and which window it belonged to, so a
refund can be applied only to that same window and never hands back a slot
the user did not pay for.
"""

from __future__ import annotations

import datetime

from bson import ObjectId
from flask import current_app, jsonify

from backend.extensions import mongo


DEEP_FOCUS_MODE = "Pro Reasoning"
QUOTA_WINDOW = datetime.timedelta(hours=24)

# Generations allowed per 24-hour window, by plan. None means unlimited.
PLAN_GENERATION_LIMITS = {
    "free": 5,
    "plus": 20,
    "pro": 100,
}

# Deep Focus (Pro Reasoning) generations allowed per 24-hour window, by plan.
# Deep Focus has its own budget and does not use the Quick limit. It runs on
# the most expensive model, so every plan is capped.
PLAN_DEEP_FOCUS_LIMITS = {
    "free": 3,
    "plus": 10,
    "pro": 30,
}

_MAX_ATTEMPTS = 4


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


def _now():
    # MongoDB stores milliseconds; truncate so the value written equals the
    # value later used to match the window exactly.
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def _aware(value):
    if isinstance(value, datetime.datetime) and value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value


def consume_generation_quota(user_id, user_doc, mode=None):
    """Charge one generation to the user's current window.

    Returns ``(error_response, charge)``. ``error_response`` is a Flask
    response tuple when the user is over their limit, otherwise None.
    ``charge`` describes what was consumed (None for unlimited plans) and
    must be stored with the generation run so it can be refunded.
    """
    is_deep = mode == DEEP_FOCUS_MODE
    limit = deep_focus_limit_for(user_doc) if is_deep else generation_limit_for(user_doc)
    if limit is None:
        return None, None

    counter = "deep_rate_limit" if is_deep else "rate_limit"
    user_object_id = ObjectId(user_id)

    for _ in range(_MAX_ATTEMPTS):
        user = mongo.db.users.find_one({"_id": user_object_id}, {"first_submission_time": 1})
        if not user:
            return (jsonify({"success": False, "message": "User not found."}), 404), None
        stored_start = user.get("first_submission_time")
        start = _aware(stored_start)
        now = _now()

        if not start or now - start >= QUOTA_WINDOW:
            # Open a new window. The filter on the old window start means only
            # one concurrent request can do this; the others retry and are
            # counted inside the new window.
            opened = mongo.db.users.update_one(
                {"_id": user_object_id, "first_submission_time": stored_start},
                {
                    "$set": {
                        "first_submission_time": now,
                        "rate_limit": 0 if is_deep else 1,
                        "deep_rate_limit": 1 if is_deep else 0,
                    }
                },
            )
            if opened.modified_count:
                return None, {"counter": counter, "window_start": now}
            continue

        charged = mongo.db.users.update_one(
            {
                "_id": user_object_id,
                "first_submission_time": stored_start,
                "$or": [{counter: {"$lt": limit}}, {counter: {"$exists": False}}],
            },
            {"$inc": {counter: 1}},
        )
        if charged.modified_count:
            return None, {"counter": counter, "window_start": stored_start}

        current = mongo.db.users.find_one({"_id": user_object_id}, {"first_submission_time": 1})
        if current and current.get("first_submission_time") == stored_start:
            return _limit_reached(limit, is_deep, now - start), None
        # The window changed under us; try again against the new one.

    return (
        jsonify({"success": False, "message": "Too many requests at once. Please try again."}),
        429,
    ), None


def release_quota_charge(user_id, charge):
    """Give a charged slot back, but only within the window it was taken from."""
    if not charge or not charge.get("counter") or not charge.get("window_start"):
        return
    counter = charge["counter"]
    if counter not in {"rate_limit", "deep_rate_limit"}:
        return
    mongo.db.users.update_one(
        {
            "_id": ObjectId(str(user_id)),
            "first_submission_time": charge["window_start"],
            counter: {"$gt": 0},
        },
        {"$inc": {counter: -1}},
    )


def _limit_reached(limit, is_deep, elapsed):
    remaining = max(QUOTA_WINDOW - elapsed, datetime.timedelta(0))
    hours = int(remaining.total_seconds()) // 3600
    minutes = (int(remaining.total_seconds()) % 3600) // 60
    if is_deep:
        message = (
            f"Deep Focus limit reached ({limit} per 24 hours). "
            f"Try Quick mode, or try Deep Focus again in {hours}h {minutes}m."
        )
    else:
        message = (
            f"Daily generation limit reached ({limit} per 24 hours). "
            f"Try again in {hours}h {minutes}m."
        )
    return jsonify({"success": False, "message": message}), 429
