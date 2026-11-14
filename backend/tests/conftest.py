"""Shared test setup.

Environment is fixed before any backend module is imported, so tests never
touch a real database, a real model, or real credentials. Tests under
``tests/integration`` need a MongoDB server and are skipped when none is
reachable; they use a throwaway database that is dropped afterwards.
"""

from __future__ import annotations

import os
import uuid

import pytest

TEST_DATABASE = f"lexinit_test_{uuid.uuid4().hex[:10]}"
MONGO_URI = os.environ.get("TEST_MONGO_URI", "mongodb://localhost:27017")

os.environ.update(
    {
        "FLASK_SECRET_KEY": "test-secret-key-not-used-anywhere-else",
        "USE_LOCAL_MONGO": "true",
        "LOCAL_MONGO_URI": MONGO_URI,
        "MONGO_DB_NAME": TEST_DATABASE,
        "CSRF_ENABLED": "false",
        "GENERATION_RESUME_ON_STARTUP": "false",
        "GENERATION_WORKER_MODE": "local",
        "GEMINI_USE_VERTEX": "false",
        "GEMINI_API_KEY": "test-key",
        "GEMINI_MODEL_NAME": "test-model",
        "GEMINI_COACH_MODEL_NAME": "",
        "MAIL_SUPPRESS_SEND": "true",
    }
)
os.environ.pop("REDIS_URL", None)

# Imported only after the environment is fixed: importing any backend module
# reads the configuration, and it must see the test database.
from helpers import build_course  # noqa: E402

QUESTION_FIELDS = {"mcq": "mcqs", "truefalse": "true_false", "oneword": "oneword"}


def _mongo_client():
    from pymongo import MongoClient

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
    client.admin.command("ping")
    return client


@pytest.fixture(scope="session")
def mongo_client():
    try:
        client = _mongo_client()
    except Exception:
        pytest.skip("MongoDB is not reachable; integration tests skipped.")
    yield client
    client.drop_database(TEST_DATABASE)
    client.close()


@pytest.fixture(scope="session")
def app(mongo_client):
    from backend import create_app

    application = create_app(resume_generation_runs=False)
    assert application.config["MONGO_DB_NAME"] == TEST_DATABASE
    return application


@pytest.fixture()
def db(app, mongo_client):
    return mongo_client[TEST_DATABASE]


@pytest.fixture()
def user(db):
    from bson import ObjectId

    document = {
        "_id": ObjectId(),
        "email": f"learner-{uuid.uuid4().hex[:12]}@example.test",
        "name": "Test Learner",
        "password": "x" * 40,
        "verified": True,
        "plan": "free",
        "rate_limit": 0,
        "deep_rate_limit": 0,
    }
    db.users.insert_one(document)
    return document


@pytest.fixture()
def client(app, user):
    web = app.test_client()
    with web.session_transaction() as session:
        session["user_id"] = str(user["_id"])
    return web


@pytest.fixture()
def course(db, user):
    document = build_course(user["_id"])
    db.sessions.insert_one(document)
    return document


@pytest.fixture(autouse=True)
def no_model_calls(request, monkeypatch):
    """Integration tests must never call a real model. Fresh assessment
    questions are produced by a deterministic stand-in instead."""
    if "integration" not in str(request.node.fspath):
        return
    import backend.routes.learning_loop as learning_loop

    counter = {"value": 0}

    def fake_refill(*, user_id, session_data, module_id, assessment_type, count):
        from pymongo import MongoClient, ReturnDocument

        database = MongoClient(MONGO_URI)[TEST_DATABASE]
        field = QUESTION_FIELDS[assessment_type.value]
        module = next(
            item for item in session_data["curriculum"]["modules"] if item["module_id"] == module_id
        )
        new_questions = []
        for _ in range(count):
            counter["value"] += 1
            question = {
                "question_id": f"refill_{counter['value']}_{uuid.uuid4().hex[:6]}",
                "question": f"Fresh {assessment_type.value} question {counter['value']}?",
                "explanation": "Fresh explanation.",
                "module_id": module_id,
                "concept_ids": [module["concepts"][0]["concept_id"]],
                "objective_ids": [module["learning_objectives"][0]["objective_id"]],
                "difficulty": "easy",
                "generation_kind": "refill",
                "misconception_map": {},
            }
            if assessment_type.value == "mcq":
                question.update({"options": ["first", "second", "third", "fourth"], "answer": 1})
            elif assessment_type.value == "truefalse":
                question["answer"] = True
            else:
                question["answer"] = "photosynthesis"
            new_questions.append(question)
        return database.sessions.find_one_and_update(
            {"_id": session_data["_id"]},
            {"$push": {field: {"$each": new_questions}}},
            return_document=ReturnDocument.AFTER,
        )

    monkeypatch.setattr(learning_loop, "_refill_questions", fake_refill)
    monkeypatch.setattr(learning_loop, "_analyze_weak_topic", lambda context: "")
