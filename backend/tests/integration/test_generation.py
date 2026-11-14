"""Course creation end to end, with every model and web call replaced.

The real orchestrator, checkpoints, validation, quota and HTTP routes run;
only the functions that would call Gemini, YouTube or web search are stubbed.
"""

import threading
import time
import uuid
from collections import Counter

import pytest

import backend.routes.content as content_routes
import backend.services.generation_jobs as jobs
from backend.lexinit.schemas.curriculum import Curriculum
from backend.lexinit.schemas.generated_content import (
    FlashcardDraft,
    MCQDraft,
    OneWordDraft,
    TrueFalseDraft,
)
from backend.lexinit.schemas.knowledge import CourseKnowledgePacks
from backend.lexinit.services.practice_generation import ModulePracticeDraft

PRACTICE_FIELDS = ("flashcards", "mcqs", "true_false", "oneword")


def make_curriculum(topic="Stubbed Topic") -> Curriculum:
    tag = uuid.uuid4().hex[:8]
    return Curriculum(
        curriculum_id=f"curriculum_{tag}",
        canonical_topic=topic,
        difficulty="easy",
        modules=[
            {
                "module_id": f"module_{tag}_{index}",
                "title": f"Module {index + 1}",
                "concepts": [
                    {
                        "concept_id": f"concept_{tag}_{index}_{position}",
                        "name": f"Concept {index + 1}.{position + 1}",
                        "difficulty": "easy",
                    }
                    for position in range(2)
                ],
                "learning_objectives": [
                    {
                        "objective_id": f"objective_{tag}_{index}",
                        "description": f"Explain the ideas of module {index + 1}.",
                        "concept_ids": [f"concept_{tag}_{index}_0"],
                    }
                ],
                "difficulty": "easy",
                "estimated_minutes": 30,
            }
            for index in range(5)
        ],
    )


def make_packs(curriculum: Curriculum) -> CourseKnowledgePacks:
    return CourseKnowledgePacks(
        curriculum_id=curriculum.curriculum_id,
        packs=[
            {
                "knowledge_pack_id": f"pack_{module.module_id}",
                "curriculum_id": curriculum.curriculum_id,
                "module_id": module.module_id,
                "module_title": module.title,
                "difficulty": "easy",
                "concept_ids": [concept.concept_id for concept in module.concepts],
                "objective_ids": [item.objective_id for item in module.learning_objectives],
                "required_concepts": [concept.name for concept in module.concepts],
                "important_facts": ["Fact one.", "Fact two."],
                "video_search_terms": ["term one", "term two"],
            }
            for module in curriculum.modules
        ],
    )


class PracticeWriter:
    """Stands in for the model when it writes a module's practice."""

    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()

    def generate_structured(self, prompt, schema, *, temperature=0.2):
        assert schema is ModulePracticeDraft
        assert "STUDY_MATERIAL" in prompt and "Study text for" in prompt
        with self.lock:
            self.calls += 1
            tag = self.calls
        return ModulePracticeDraft(
            flashcards=[FlashcardDraft(question=f"Card {tag}.{i}?", answer="answer") for i in range(2)],
            mcqs=[
                MCQDraft(
                    question=f"Choice {tag}.{i}?",
                    options=["a", "b", "c", "d"],
                    correct_option_index=1,
                    explanation="Because b.",
                )
                for i in range(3)
            ],
            true_false=[
                TrueFalseDraft(question=f"Statement {tag}.{i}.", answer=True, explanation="True.")
                for i in range(3)
            ],
            one_word=[
                OneWordDraft(question=f"Word {tag}.{i}?", answer="term", explanation="The term.")
                for i in range(3)
            ],
        )


@pytest.fixture()
def stubs(monkeypatch):
    """Replace every outside call. Returns counters and switches for tests."""
    state = {
        "curriculum": None,
        "material_calls": Counter(),
        "writer": PracticeWriter(),
        "fail_material_for": set(),
        "verified": [],
    }

    def plan_curriculum(topic, difficulty, model_name=None, source_context=None, learner_context=None):
        state["curriculum"] = make_curriculum(topic)
        return state["curriculum"]

    def study_material(topic, subtopic, difflvl, mode, model_name=None, pack=None):
        state["material_calls"][subtopic] += 1
        if subtopic in state["fail_material_for"]:
            raise RuntimeError("simulated model outage")
        return f"Study text for {subtopic}. " * 30

    def course_content(topic, difflevel, model_name=None, curriculum=None, knowledge_packs=None):
        packs = {pack.module_id: pack for pack in knowledge_packs.packs}
        return [
            {
                "module_id": module.module_id,
                "subtopic": module.title,
                "link": f"https://www.youtube.com/watch?v=video{index:06d}",
                "video_id": f"video{index:06d}",
                "concept_ids": [module.concepts[0].concept_id],
                "objective_ids": [module.learning_objectives[0].objective_id],
                "knowledge_pack_id": packs[module.module_id].knowledge_pack_id,
                "video_relevance_score": 0.5,
            }
            for index, module in enumerate(curriculum.modules)
        ]

    def verify(generator, questions):
        state["verified"].append(len(questions))
        return questions

    monkeypatch.setattr(content_routes, "canonicalize_topic", lambda topic: topic)
    monkeypatch.setattr(jobs, "moderate_content", lambda topic: "forbidden" not in topic.lower())
    monkeypatch.setattr(jobs, "plan_curriculum", plan_curriculum)
    monkeypatch.setattr(
        jobs, "build_knowledge_packs", lambda curriculum, model_name=None, **kwargs: make_packs(curriculum)
    )
    monkeypatch.setattr(jobs, "generate_module_study_material", study_material)
    monkeypatch.setattr(jobs, "get_gemini_model", lambda *args, **kwargs: state["writer"])
    monkeypatch.setattr(jobs, "verify_answer_keys", verify)
    monkeypatch.setattr(jobs, "get_course_content", course_content)
    monkeypatch.setattr(jobs, "get_learningpath", lambda topic, difflvl, model_name=None: "A learning path.")
    monkeypatch.setattr(
        jobs, "get_additional_resources_links", lambda topic: [{"title": "Resource", "link": "https://example.test"}]
    )
    return state


def start_run(client, topic="Stubbed Topic", mode="Basic"):
    response = client.post(
        "/api/v1/generation-runs",
        json={"topic": topic, "difflevel": "easy", "mode": mode},
        headers={"Idempotency-Key": f"test-{uuid.uuid4().hex}"},
    )
    return response, response.get_json()


def wait_for(db, run_id, *, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = db.generation_runs.find_one({"_id": run_id})
        if run and run["status"] in {"completed", "failed", "cancelled"} and not run.get("lease_owner"):
            return run
        time.sleep(0.1)
    raise AssertionError(f"run did not finish: {run and run['status']} at {run and run['stage']}")


def quota(db, user):
    document = db.users.find_one({"_id": user["_id"]})
    return document.get("rate_limit", 0), document.get("deep_rate_limit", 0)


def test_a_course_is_created_with_every_module_complete(client, db, user, stubs):
    response, body = start_run(client)
    assert response.status_code == 202 and body["queued"] is True
    run = wait_for(db, body["job_id"])
    assert run["status"] == "completed" and run["progress"] == 100 and not run["failed_steps"]

    course = db.sessions.find_one({"generation_run_id": run["_id"]})
    module_ids = [module["module_id"] for module in course["curriculum"]["modules"]]
    assert [item["module_id"] for item in course["study_materials"]] == module_ids
    assert all(item["study_material"].startswith("Study text for") for item in course["study_materials"])
    for field in PRACTICE_FIELDS:
        counts = Counter(item["module_id"] for item in course[field])
        assert [counts[module_id] for module_id in module_ids] == [2] * 5, field
        assert all(item["grounded_in"] == "study_material" for item in course[field])
        assert len({item["question"] for item in course[field]}) == 10
    assert len(course["course_content"]) == 5 and course["learningpath"] == "A learning path."

    # One material and one practice call per module, and one answer-key check per module.
    assert sum(stubs["material_calls"].values()) == 5 and stubs["writer"].calls == 5
    assert stubs["verified"] == [9] * 5
    steps = run["completed_steps"]
    assert sum(step.startswith("module_material:") for step in steps) == 5
    assert sum(step.startswith("module_practice:") for step in steps) == 5
    assert quota(db, user) == (1, 0)

    # The saved course works with the rest of the app and hides its answers.
    public = client.get(f"/api/v1/sessions/{course['_id']}").get_json()["session"]
    assert "answer" not in public["mcqs"][0]
    overview = client.get(f"/api/v1/sessions/{course['_id']}/course").get_json()
    assert overview["total_modules"] == 5 and overview["final_assessment"]["state"] == "locked"


def test_deep_focus_uses_its_own_budget(client, db, user, stubs):
    _, body = start_run(client, mode="Pro Reasoning")
    assert wait_for(db, body["job_id"])["status"] == "completed"
    assert quota(db, user) == (0, 1)


def test_the_same_request_reuses_the_saved_course(client, db, user, stubs):
    _, first = start_run(client)
    wait_for(db, first["job_id"])
    response, second = start_run(client)
    assert response.status_code == 200 and second.get("cached") is True
    assert db.sessions.count_documents({"user_id": user["_id"]}) == 1
    assert quota(db, user) == (1, 0)  # the cached course cost nothing


def test_an_unsafe_topic_fails_and_refunds_the_generation(client, db, user, stubs):
    _, body = start_run(client, topic="A forbidden topic")
    run = wait_for(db, body["job_id"])
    assert run["status"] == "failed" and run["error"]["step"] == "safety"
    assert db.sessions.count_documents({"user_id": user["_id"]}) == 0
    assert quota(db, user) == (0, 0)


def test_a_failed_module_is_retried_alone(client, db, user, stubs):
    stubs["fail_material_for"] = {"Module 3"}
    _, body = start_run(client)
    run = wait_for(db, body["job_id"])
    assert run["status"] == "failed" and run["error"]["retryable"] is True
    assert "Study Materials" in run["message"]
    assert any(step.startswith("module_material:") for step in run["failed_steps"])
    assert db.sessions.count_documents({"user_id": user["_id"]}) == 0
    assert quota(db, user) == (0, 0)  # refunded
    saved = sum(step.startswith("module_material:") for step in run["completed_steps"])
    assert saved == 4

    stubs["fail_material_for"] = set()
    materials_before = sum(stubs["material_calls"].values())
    practice_before = stubs["writer"].calls
    retry = client.post(f"/api/v1/generation-runs/{run['_id']}/retry")
    assert retry.status_code == 202
    run = wait_for(db, run["_id"])
    assert run["status"] == "completed" and run["attempt"] == 2
    # Only the failed module's material and practice were written again.
    assert sum(stubs["material_calls"].values()) - materials_before == 1
    assert stubs["writer"].calls - practice_before == 1
    assert db.sessions.count_documents({"generation_run_id": run["_id"]}) == 1
    assert quota(db, user) == (1, 0)


def test_two_modules_with_the_same_question_are_rewritten_on_retry(client, db, user, stubs, monkeypatch):
    class RepeatingWriter(PracticeWriter):
        def generate_structured(self, prompt, schema, *, temperature=0.2):
            draft = super().generate_structured(prompt, schema, temperature=temperature)
            draft.mcqs[0] = draft.mcqs[0].model_copy(update={"question": "The same question everywhere?"})
            return draft

    stubs["writer"] = RepeatingWriter()
    _, body = start_run(client)
    run = wait_for(db, body["job_id"])
    assert run["status"] == "failed"
    # The module practice was cleared so a retry does not fail the same way.
    assert not any(step.startswith("module_practice:") for step in run["completed_steps"])
    assert sum(step.startswith("module_material:") for step in run["completed_steps"]) == 5

    stubs["writer"] = PracticeWriter()
    assert client.post(f"/api/v1/generation-runs/{run['_id']}/retry").status_code == 202
    run = wait_for(db, run["_id"])
    assert run["status"] == "completed"
    assert sum(stubs["material_calls"].values()) == 5  # materials were kept


def test_a_cancelled_run_saves_nothing(client, db, user, stubs, monkeypatch):
    started = threading.Event()
    release = threading.Event()

    def slow_material(topic, subtopic, difflvl, mode, model_name=None, pack=None):
        started.set()
        release.wait(timeout=10)
        return f"Study text for {subtopic}. " * 30

    monkeypatch.setattr(jobs, "generate_module_study_material", slow_material)
    _, body = start_run(client)
    assert started.wait(timeout=10)
    cancel = client.post(f"/api/v1/generation-runs/{body['job_id']}/cancel")
    assert cancel.status_code == 200
    release.set()
    run = wait_for(db, body["job_id"])
    assert run["status"] == "cancelled"
    assert db.sessions.count_documents({"user_id": user["_id"]}) == 0
    assert quota(db, user) == (0, 0)
