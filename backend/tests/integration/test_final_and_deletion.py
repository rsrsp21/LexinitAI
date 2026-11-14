"""Final assessment lifecycle, the badge rule, and course deletion."""

import datetime

import pytest
from bson import ObjectId

from backend.lexinit.api.errors import ApiError
from backend.lexinit.repositories import MongoAdaptiveLearningRepository
from backend.lexinit.schemas.generated_content import MCQDraft, OneWordDraft, TrueFalseDraft
from backend.lexinit.services import AdaptiveLearningService
from backend.lexinit.services.course_progress import CourseProgressService
from backend.lexinit.services.final_assessment import (
    FINAL_QUESTION_COUNT,
    FinalAssessmentService,
    FinalSetDraft,
)
from helpers import build_course


class FakeFinalWriter:
    """Writes a valid final set covering every module, new text each call."""

    def __init__(self, course):
        self.concepts = [
            module["concepts"][0]["concept_id"] for module in course["curriculum"]["modules"]
        ]
        self.calls = 0

    def generate_structured(self, prompt, schema, *, temperature=0.2):
        assert schema is FinalSetDraft
        self.calls += 1
        tag = f"set {self.calls}"

        def concept(index):
            return [self.concepts[index % len(self.concepts)]]

        return FinalSetDraft(
            mcqs=[
                MCQDraft(
                    question=f"Final choice {tag} number {i}?",
                    options=["first", "second", "third", "fourth"],
                    correct_option_index=1,
                    explanation="The second option.",
                    concept_ids=concept(i),
                )
                for i in range(5)
            ],
            true_false=[
                TrueFalseDraft(
                    question=f"Final statement {tag} number {i}.",
                    answer=True,
                    explanation="It is true.",
                    concept_ids=concept(i),
                )
                for i in range(4)
            ],
            one_word=[
                OneWordDraft(
                    question=f"Final word {tag} number {i}?",
                    answer="photosynthesis",
                    explanation="The term.",
                    concept_ids=concept(i),
                )
                for i in range(3)
            ],
        )


class UnavailableVerifier:
    def generate_structured(self, *args, **kwargs):
        raise RuntimeError("no verifier in tests")


def pass_every_module(db, user, course):
    now = datetime.datetime.now(datetime.timezone.utc)
    for module in course["curriculum"]["modules"]:
        for kind in ("mcq", "truefalse", "oneword"):
            db.assessment_submissions.insert_one(
                {
                    "_id": ObjectId(),
                    "user_id": user["_id"],
                    "session_id": course["_id"],
                    "assessment_type": kind,
                    "score": 4,
                    "total": 4,
                    "module_id": module["module_id"],
                    "created_at": now,
                    "questions": [],
                    "feedback": [],
                }
            )


@pytest.fixture()
def final_service(db, course):
    repository = MongoAdaptiveLearningRepository(
        evidence_collection=db.mastery_evidence,
        mastery_collection=db.concept_mastery,
        decisions_collection=db.adaptation_decisions,
    )
    return FinalAssessmentService(
        db=db,
        generator=FakeFinalWriter(course),
        adaptive_service=AdaptiveLearningService(repository),
        course_progress=CourseProgressService(db),
        verifier=UnavailableVerifier(),
    )


def answers(db, final_id, *, correct=True):
    questions = db.final_assessments.find_one({"_id": final_id})["questions"]
    if correct:
        return [question["answer"] for question in questions]
    wrong = {"mcq": 0, "truefalse": False, "oneword": "wrongword"}
    return [wrong[question["type"]] for question in questions]


def loader(db):
    return lambda session_id: db.sessions.find_one({"_id": session_id})


def state(db, user, course):
    return CourseProgressService(db).course(user["_id"], course)


def test_the_final_is_locked_until_every_module_is_passed(db, user, course, final_service):
    assert state(db, user, course)["final_assessment"]["state"] == "locked"
    with pytest.raises(ApiError) as error:
        final_service.start(user_id=user["_id"], session_data=course)
    assert error.value.code == "final_locked"


def test_final_assessment_lifecycle(db, user, course, final_service):
    pass_every_module(db, user, course)
    assert state(db, user, course)["final_assessment"]["state"] == "available"

    first = final_service.start(user_id=user["_id"], session_data=course)
    assert len(first["questions"]) == FINAL_QUESTION_COUNT
    assert all("answer" not in question and "explanation" not in question for question in first["questions"])
    # Starting again resumes the same attempt.
    assert final_service.start(user_id=user["_id"], session_data=course)["final_id"] == first["final_id"]
    assert state(db, user, course)["final_assessment"]["state"] == "in_progress"

    with pytest.raises(ApiError) as error:
        final_service.submit(
            user_id=user["_id"], final_id=first["final_id"], answers=[1], session_data_loader=loader(db)
        )
    assert error.value.code == "final_incomplete"

    failed = final_service.submit(
        user_id=user["_id"],
        final_id=first["final_id"],
        answers=answers(db, first["final_id"], correct=False),
        session_data_loader=loader(db),
    )["result"]
    assert failed["passed"] is False and failed["percent"] == 0
    assert failed["concepts"] and failed["concepts"][0]["missed"] > 0
    assert db.mastery_evidence.count_documents(
        {"user_id": user["_id"], "source_kind": "final_assessment"}
    ) >= FINAL_QUESTION_COUNT

    course_state = state(db, user, course)["final_assessment"]
    assert course_state["state"] == "cooldown" and course_state["retry_available_at"]
    with pytest.raises(ApiError) as error:
        final_service.start(user_id=user["_id"], session_data=course)
    assert error.value.code == "final_cooldown"

    # A day later the retake uses new questions.
    db.final_assessments.update_many(
        {"user_id": user["_id"]},
        {"$set": {"completed_at": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)}},
    )
    retake = final_service.start(user_id=user["_id"], session_data=course)
    first_text = {q["question"] for q in db.final_assessments.find_one({"_id": first["final_id"]})["questions"]}
    assert not first_text & {question["question"] for question in retake["questions"]}

    passed = final_service.submit(
        user_id=user["_id"],
        final_id=retake["final_id"],
        answers=answers(db, retake["final_id"]),
        session_data_loader=loader(db),
    )["result"]
    assert passed["passed"] is True and passed["percent"] == 100
    # Submitting again never changes a recorded result.
    again = final_service.submit(
        user_id=user["_id"],
        final_id=retake["final_id"],
        answers=answers(db, retake["final_id"], correct=False),
        session_data_loader=loader(db),
    )["result"]
    assert again["percent"] == 100
    with pytest.raises(ApiError) as error:
        final_service.start(user_id=user["_id"], session_data=course)
    assert error.value.code == "final_already_passed"


def test_the_badge_needs_every_activity_and_the_final(db, user, course, final_service):
    pass_every_module(db, user, course)
    now = datetime.datetime.now(datetime.timezone.utc)
    for module in course["curriculum"]["modules"]:
        for kind in ("material", "flashcards"):
            db.course_activity_progress.insert_one(
                {
                    "user_id": user["_id"],
                    "session_id": course["_id"],
                    "module_id": module["module_id"],
                    "activity_id": f"{module['module_id']}:{kind}",
                    "activity_type": kind,
                    "status": "completed",
                    "completed_at": now,
                }
            )
    before = state(db, user, course)
    assert before["status"] == "in_progress" and before["progress_percent"] < 100

    final = final_service.start(user_id=user["_id"], session_data=course)
    final_service.submit(
        user_id=user["_id"],
        final_id=final["final_id"],
        answers=answers(db, final["final_id"]),
        session_data_loader=loader(db),
    )
    after = state(db, user, course)
    assert after["status"] == "completed" and after["progress_percent"] == 100


def test_deleting_a_course_removes_everything_it_owns(client, db, user, course):
    other = build_course(user["_id"], topic="Kept Course")
    db.sessions.insert_one(other)
    now = datetime.datetime.now(datetime.timezone.utc)
    concept = course["curriculum"]["modules"][0]["concepts"][0]["concept_id"]
    for owner in (course, other):
        owner_concept = owner["curriculum"]["modules"][0]["concepts"][0]["concept_id"]
        db.assessment_submissions.insert_one(
            {"_id": ObjectId(), "user_id": user["_id"], "session_id": owner["_id"], "assessment_type": "mcq", "score": 1, "total": 2, "created_at": now}
        )
        db.mastery_evidence.insert_one(
            {
                "_id": f"evidence_{ObjectId()}",
                "evidence_id": f"evidence_{ObjectId()}",
                "user_id": user["_id"],
                "submission_id": "s",
                "session_id": str(owner["_id"]),
                "question_id": "q",
                "concept_id": owner_concept,
                "concept_label": "Concept",
                "correct": True,
                "difficulty": "easy",
                "observed_at": now,
            }
        )
        db.concept_mastery.insert_one(
            {"user_id": user["_id"], "concept_id": owner_concept, "mastery_probability": 0.6, "last_practiced_at": now, "next_review_at": now}
        )
    for name in ("final_assessments", "coach_checks", "coach_items"):
        db[name].insert_one({"_id": f"{name}_{ObjectId()}", "user_id": user["_id"], "session_id": course["_id"]})
    db.course_goals.insert_one({"user_id": user["_id"], "session_id": course["_id"], "target_date": "2030-01-01"})

    wrong = client.delete(f"/api/v1/sessions/{course['_id']}", json={"confirm_code": "000000"})
    assert wrong.status_code == 400 and db.sessions.count_documents({"_id": course["_id"]}) == 1

    response = client.delete(
        f"/api/v1/sessions/{course['_id']}", json={"confirm_code": str(course["_id"])[-6:]}
    )
    assert response.status_code == 200

    keys = [course["_id"], str(course["_id"])]
    for name in db.list_collection_names():
        assert db[name].count_documents({"user_id": user["_id"], "session_id": {"$in": keys}}) == 0, name
    assert db.sessions.count_documents({"_id": course["_id"]}) == 0
    assert db.concept_mastery.count_documents({"user_id": user["_id"], "concept_id": concept}) == 0

    # The other course is untouched.
    assert db.sessions.count_documents({"_id": other["_id"]}) == 1
    assert db.assessment_submissions.count_documents({"session_id": other["_id"]}) == 1
    assert db.concept_mastery.count_documents({"user_id": user["_id"]}) == 1
    courses = client.get("/api/v1/courses").get_json()["courses"]
    assert [item["topic"] for item in courses] == ["Kept Course"]
    assert client.get(f"/api/v1/sessions/{course['_id']}/course").status_code == 404
