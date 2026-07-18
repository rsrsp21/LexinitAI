from bson import ObjectId

from backend.extensions import mongo


def normalize_topic(topic):
    return " ".join((topic or "").strip().lower().split())


def session_lookup_id(session_id):
    values = [session_id]
    try:
        values.append(ObjectId(session_id))
    except Exception:
        pass
    return values


def list_user_sessions(user_id, limit=None, query=None):
    user_object_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    filter_query = {"user_id": user_object_id}
    if query:
        filter_query["topic"] = {"$regex": query.strip(), "$options": "i"}

    cursor = mongo.db.sessions.find(filter_query).sort("created_at", -1)
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)


def get_user_session(user_id, session_id):
    user_object_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    return mongo.db.sessions.find_one(
        {
            "_id": {"$in": session_lookup_id(session_id)},
            "user_id": user_object_id,
        }
    )


def delete_user_session(user_id, session_id):
    user_object_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    return mongo.db.sessions.delete_one(
        {
            "_id": {"$in": session_lookup_id(session_id)},
            "user_id": user_object_id,
        }
    )


def find_cached_session(
    user_id, topic, difflvl, mode, personalization_profile=None
):
    user_object_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    normalized_topic = normalize_topic(topic)
    normalized_level = (difflvl or "").strip().lower()
    normalized_mode = mode or "Basic"
    return mongo.db.sessions.find_one(
        {
            "user_id": user_object_id,
            "normalized_topic": normalized_topic,
            "difficulty_level": normalized_level,
            "generation_mode": normalized_mode,
            "personalization_profile": personalization_profile,
        },
        sort=[("created_at", -1)],
    )
