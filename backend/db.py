import threading
from urllib.parse import urlsplit

import dns.resolver
from bson import ObjectId
from flask import current_app, has_app_context
from pymongo.errors import DuplicateKeyError, OperationFailure, PyMongoError
from pymongo import MongoClient


DEFAULT_DATABASE_NAME = "lexinit"

USER_SCHEMA = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["email", "password", "verified"],
        "properties": {
            "email": {
                "bsonType": "string",
                "description": "User email is required and must be a string.",
                "maxLength": 254,
                "pattern": r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
            },
            "name": {
                "bsonType": "string",
                "description": "Display name is required.",
                "minLength": 2,
                "maxLength": 80,
            },
            "password": {
                "bsonType": "string",
                "description": "Hashed password is required.",
                "minLength": 20,
            },
            "verified": {"bsonType": "bool"},
            "agreed_terms": {"bsonType": ["bool", "null"]},
            "terms_accepted_at": {"bsonType": ["double", "int", "long", "null"]},
            "agreed_privacy": {"bsonType": ["bool", "null"]},
            "privacy_accepted_at": {"bsonType": ["double", "int", "long", "null"]},
            "legal_version": {"bsonType": ["string", "null"], "maxLength": 32},
            "forgot_password": {"bsonType": ["bool", "null"]},
            "profile_type": {
                "enum": ["student", "professional", "independent", None],
            },
            "institution_name": {"bsonType": ["string", "null"], "maxLength": 120},
            "grade_or_class": {"bsonType": ["string", "null"], "maxLength": 80},
            "organization_name": {"bsonType": ["string", "null"], "maxLength": 120},
            "professional_role": {"bsonType": ["string", "null"], "maxLength": 120},
            "work_experience_years": {
                "bsonType": ["int", "long", "null"],
                "minimum": 0,
                "maximum": 70,
            },
            "profile_updated_at": {"bsonType": ["date", "null"]},
            "profile_complete": {"bsonType": ["bool", "null"]},
        },
    }
}


def configure_mongo_dns(app):
    mongo_uri = app.config.get("MONGO_URI") or ""
    nameservers = app.config.get("MONGO_DNS_NAMESERVERS") or []
    if not mongo_uri.startswith("mongodb+srv://") or not nameservers:
        return

    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = nameservers
    resolver.timeout = 3
    resolver.lifetime = 6
    dns.resolver.default_resolver = resolver


def database_name_from_uri(uri):
    path_name = urlsplit(uri).path.strip("/")
    return path_name or None


def ensure_database_schema(app):
    try:
        db = app.extensions["mongo"].get_db()
        collections = db.list_collection_names()
        if "users" not in collections:
            db.create_collection("users", validator=USER_SCHEMA, validationLevel="moderate")
        else:
            db.command(
                "collMod",
                "users",
                validator=USER_SCHEMA,
                validationLevel="moderate",
            )

        create_index_ignoring_equivalent_conflict(db.users, "email", unique=True)
        create_index_ignoring_equivalent_conflict(db.user_verify, "email", unique=True)
        create_index_ignoring_equivalent_conflict(db.password_resets, "email", unique=True)
        create_index_ignoring_equivalent_conflict(db.waitlist, "email", unique=True)
        create_index_ignoring_equivalent_conflict(db.password_resets, "reset_expires_at", expireAfterSeconds=0)
        create_index_ignoring_equivalent_conflict(db.sessions, "user_id")
        create_index_ignoring_equivalent_conflict(db.sessions, [("user_id", 1), ("created_at", -1)])
        create_index_ignoring_equivalent_conflict(
            db.assessment_submissions,
            [("user_id", 1), ("created_at", -1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.assessment_submissions,
            [("user_id", 1), ("session_id", 1), ("assessment_type", 1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.assessment_submissions,
            "attempt_id",
            unique=True,
            sparse=True,
        )
        create_index_ignoring_equivalent_conflict(
            db.assessment_attempts,
            [("user_id", 1), ("start_idempotency_key", 1)],
            unique=True,
        )
        create_index_ignoring_equivalent_conflict(
            db.assessment_attempts,
            [("user_id", 1), ("status", 1), ("updated_at", -1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.assessment_attempts,
            [("user_id", 1), ("session_id", 1), ("status", 1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.assessment_attempts,
            "expires_at",
            expireAfterSeconds=86400,
        )
        create_index_ignoring_equivalent_conflict(
            db.assessment_question_bank,
            [("user_id", 1), ("session_id", 1), ("assessment_type", 1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.mastery_evidence,
            [("user_id", 1), ("concept_id", 1), ("observed_at", 1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.concept_mastery,
            [("user_id", 1), ("concept_id", 1)],
            unique=True,
        )
        create_index_ignoring_equivalent_conflict(
            db.adaptation_decisions,
            [("user_id", 1), ("created_at", -1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.review_events,
            [("user_id", 1), ("idempotency_key", 1)],
            unique=True,
        )
        create_index_ignoring_equivalent_conflict(
            db.review_events,
            [("user_id", 1), ("concept_id", 1), ("created_at", -1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.video_progress,
            [("user_id", 1), ("session_id", 1), ("video_id", 1)],
            unique=True,
        )
        create_index_ignoring_equivalent_conflict(
            db.course_activity_progress,
            [("user_id", 1), ("session_id", 1), ("activity_id", 1)],
            unique=True,
        )
        create_index_ignoring_equivalent_conflict(
            db.course_module_unlocks,
            [("user_id", 1), ("session_id", 1), ("module_id", 1)],
            unique=True,
        )
        create_index_ignoring_equivalent_conflict(
            db.video_retrieval_events,
            [("user_id", 1), ("idempotency_key", 1)],
            unique=True,
        )
        create_index_ignoring_equivalent_conflict(
            db.video_retrieval_events,
            [("user_id", 1), ("session_id", 1), ("created_at", -1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.video_study_guides,
            [("session_id", 1), ("video_id", 1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.source_documents,
            [("user_id", 1), ("created_at", -1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.source_documents,
            [("user_id", 1), ("sha256", 1), ("status", 1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.source_pages,
            [("user_id", 1), ("source_id", 1), ("page_number", 1)],
            unique=True,
        )
        create_index_ignoring_equivalent_conflict(
            db.source_chunks,
            [("user_id", 1), ("source_id", 1), ("page_number", 1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.sessions,
            [("user_id", 1), ("normalized_topic", 1), ("difficulty_level", 1), ("generation_mode", 1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.sessions,
            "generation_run_id",
            unique=True,
            sparse=True,
        )
        create_index_ignoring_equivalent_conflict(
            db.generation_runs,
            [("user_id", 1), ("idempotency_key", 1)],
            unique=True,
        )
        create_index_ignoring_equivalent_conflict(
            db.generation_runs,
            [("user_id", 1), ("status", 1), ("updated_at", -1)],
        )
        create_index_ignoring_equivalent_conflict(
            db.generation_runs,
            [("status", 1), ("lease_expires_at", 1)],
        )
        create_index_ignoring_equivalent_conflict(
            db[app.config.get("SERVER_SESSION_COLLECTION", "server_sessions")],
            "expires_at",
            expireAfterSeconds=0,
        )
        migrate_embedded_sessions(db)
    except PyMongoError as exc:
        app.logger.warning("Could not ensure MongoDB schema: %s", exc)


def create_index_ignoring_equivalent_conflict(collection, keys, **kwargs):
    try:
        return collection.create_index(keys, **kwargs)
    except OperationFailure as exc:
        if exc.code == 85:
            return None
        raise


def migrate_embedded_sessions(db):
    for user in db.users.find({"sessions.0": {"$exists": True}}, {"sessions": 1}):
        user_id = user["_id"]
        for session_data in user.get("sessions", []):
            session_doc = dict(session_data)
            session_doc["_id"] = session_doc.get("_id") or ObjectId()
            session_doc["user_id"] = user_id
            session_doc.setdefault("normalized_topic", normalize_topic_for_storage(session_doc.get("topic")))
            if session_doc.get("difficulty_level"):
                session_doc["difficulty_level"] = str(session_doc["difficulty_level"]).strip().lower()
            session_doc.setdefault("generation_mode", session_doc.get("mode") or "Basic")
            try:
                db.sessions.insert_one(session_doc)
            except DuplicateKeyError:
                pass
        db.users.update_one({"_id": user_id}, {"$unset": {"sessions": ""}})


def normalize_topic_for_storage(topic):
    return " ".join((topic or "").strip().lower().split())


class MongoDatabaseProxy:
    def __init__(self, extension):
        self._extension = extension

    def __getattr__(self, collection_name):
        if collection_name.startswith("__"):
            raise AttributeError(collection_name)
        return self._extension.get_db()[collection_name]

    def __getitem__(self, collection_name):
        return self._extension.get_db()[collection_name]

    def command(self, *args, **kwargs):
        return self._extension.get_db().command(*args, **kwargs)


class LazyMongo:
    def __init__(self):
        self._app = None
        self._client = None
        self._lock = threading.Lock()
        self.db = MongoDatabaseProxy(self)

    def init_app(self, app):
        self._app = app
        configure_mongo_dns(app)
        app.extensions["mongo"] = self

    @property
    def cx(self):
        return self.get_client()

    def _get_app(self):
        if has_app_context():
            return current_app._get_current_object()
        if self._app is not None:
            return self._app
        raise RuntimeError("Mongo has not been initialized with a Flask app.")

    def get_client(self):
        if self._client is not None:
            return self._client

        with self._lock:
            if self._client is None:
                app = self._get_app()
                mongo_uri = app.config.get("MONGO_URI")
                if not mongo_uri:
                    raise RuntimeError("MONGO_URI is not configured.")
                self._client = MongoClient(mongo_uri, connect=False)

        return self._client

    def _db_name(self, app):
        mongo_uri = app.config.get("MONGO_URI") or ""
        return (
            app.config.get("MONGO_DB_NAME")
            or database_name_from_uri(mongo_uri)
            or DEFAULT_DATABASE_NAME
        )

    def get_db(self):
        app = self._get_app()
        return self.get_client()[self._db_name(app)]

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None
