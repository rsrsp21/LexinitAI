"""Boosters: eligibility, creation, re-check, and the daily allowance."""

import datetime

import pytest

from backend.lexinit.api.errors import ApiError
from backend.lexinit.repositories import MongoAdaptiveLearningRepository
from backend.lexinit.schemas.generated_content import MCQDraft
from backend.lexinit.services.booster import (
    BOOSTER_QUESTIONS,
    BoosterDraft,
    BoosterService,
)
from backend.lexinit.services.concept_coach import ConceptCoachService


class FakeBoosterWriter:
    def __init__(self):
        self.prompts = []

    def generate_structured(self, prompt, schema, *, temperature=0.2):
        assert schema is BoosterDraft
        self.prompts.append(prompt)
        number = len(self.prompts)
        return BoosterDraft(
            title="Fixing the weak concept",
            lesson="A clear second explanation. " * 20,
            key_points=["Point one.", "Point two.", "Point three."],
            questions=[
                MCQDraft(
                    question=f"Booster {number} question {index}?",
                    options=["first", "second", "third", "fourth"],
                    correct_option_index=2,
                    explanation="The third option.",
                )
                for index in range(BOOSTER_QUESTIONS)
            ],
        )


class UnavailableVerifier:
    def generate_structured(self, *args, **kwargs):
        raise RuntimeError("no verifier in tests")


@pytest.fixture()
def services(db):
    writer = FakeBoosterWriter()
    coach = ConceptCoachService(
        db=db,
        generator=writer,
        adaptive_repository=MongoAdaptiveLearningRepository(
            evidence_collection=db.mastery_evidence,
            mastery_collection=db.concept_mastery,
            decisions_collection=db.adaptation_decisions,
        ),
    )
    return BoosterService(coach=coach, generator=writer, verifier=UnavailableVerifier()), coach, writer


def make_weak(db, user, course, *, module_index=0, attempts=4, probability=0.2):
    concept = course["curriculum"]["modules"][module_index]["concepts"][0]
    now = datetime.datetime.now(datetime.timezone.utc)
    db.concept_mastery.insert_one(
        {
            "user_id": user["_id"],
            "concept_id": concept["concept_id"],
            "concept_label": concept["name"],
            "mastery_probability": probability,
            "attempts": attempts,
            "last_practiced_at": now,
            "next_review_at": now + datetime.timedelta(days=1),
        }
    )
    return concept


def ids(user, course):
    return {"user_id": str(user["_id"]), "session_id": str(course["_id"])}


def test_no_booster_without_a_concept_that_is_still_weak(db, user, course, services):
    booster, _, _ = services
    assert booster.status(**ids(user, course))["eligible"] is False
    # One wrong answer is not "still weak after practice".
    make_weak(db, user, course, attempts=1)
    assert booster.status(**ids(user, course))["eligible"] is False
    with pytest.raises(ApiError) as error:
        booster.create(**ids(user, course))
    assert error.value.code == "booster_not_needed"


def test_a_booster_targets_the_weakest_concepts_and_closes_the_gap(db, user, course, services):
    booster, coach, writer = services
    weakest = make_weak(db, user, course, module_index=1, probability=0.1)
    make_weak(db, user, course, module_index=2, probability=0.3)
    make_weak(db, user, course, module_index=3, probability=0.9)  # strong: not a target

    status = booster.status(**ids(user, course))
    assert status["eligible"] and status["remaining_today"] == 2
    assert [item["concept_id"] for item in status["concepts"]][0] == weakest["concept_id"]
    assert len(status["concepts"]) == 2

    created = booster.create(**ids(user, course))
    assert created["total"] == BOOSTER_QUESTIONS and created["completed"] is False
    assert created["lesson"] and len(created["key_points"]) == 3
    assert all("result" not in check for check in created["checks"])
    assert weakest["name"] in writer.prompts[0]
    # An unfinished booster is returned again instead of writing another.
    assert booster.create(**ids(user, course))["booster_id"] == created["booster_id"]
    assert len(writer.prompts) == 1

    for check in created["checks"]:
        stored = db.coach_checks.find_one({"_id": check["check_id"]})
        coach.answer_check(user_id=str(user["_id"]), check_id=check["check_id"], answer=stored["answer"])

    finished = booster.status(**ids(user, course))["booster"]
    assert finished["completed"] and finished["percent"] == 100 and finished["gap_closed"]
    target = next(item for item in finished["concepts"] if item["concept_id"] == weakest["concept_id"])
    assert target["current_mastery"] > target["mastery_before"]
    assert booster.status(**ids(user, course))["remaining_today"] == 1


def test_a_failed_booster_is_not_marked_as_closing_the_gap(db, user, course, services):
    booster, coach, _ = services
    make_weak(db, user, course)
    created = booster.create(**ids(user, course))
    for check in created["checks"]:
        stored = db.coach_checks.find_one({"_id": check["check_id"]})
        coach.answer_check(
            user_id=str(user["_id"]), check_id=check["check_id"], answer=(stored["answer"] + 1) % 4
        )
    finished = booster.status(**ids(user, course))["booster"]
    assert finished["completed"] and finished["percent"] == 0 and finished["gap_closed"] is False


def test_the_daily_allowance_is_enforced(db, user, course, services):
    booster, _, _ = services
    make_weak(db, user, course)
    now = datetime.datetime.now(datetime.timezone.utc)
    for index in range(2):
        db.coach_items.insert_one(
            {
                "_id": f"booster_used_{user['_id']}_{index}",
                "user_id": user["_id"],
                "kind": "booster",
                "session_id": "another-course",
                "concept_ids": [],
                "concepts": [],
                "created_at": now,
            }
        )
    assert booster.status(**ids(user, course))["remaining_today"] == 0
    with pytest.raises(ApiError) as error:
        booster.create(**ids(user, course))
    assert error.value.code == "booster_limit_reached" and error.value.status_code == 429


def test_booster_routes_require_the_course_owner(client, course):
    response = client.get(f"/api/v1/coach/sessions/{course['_id']}/booster")
    assert response.status_code == 200 and response.get_json()["eligible"] is False
    assert client.get("/api/v1/coach/sessions/ffffffffffffffffffffffff/booster").status_code == 404
