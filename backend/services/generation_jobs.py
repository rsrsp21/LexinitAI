from __future__ import annotations

import datetime
import os
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, TypedDict

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from backend.extensions import mongo
from backend.lexinit.schemas import Curriculum
from backend.lexinit.schemas.knowledge import CourseKnowledgePacks
from backend.lexinit.services import plan_curriculum
from backend.lexinit.services.knowledge_packs import build_knowledge_packs
from backend.lexinit.services.learner_context import (
    learner_context_instruction,
    learner_context_snapshot,
)
from backend.session_store import find_cached_session, normalize_topic
from backend.services.content_generation import (
    get_additional_resources_links,
    get_course_content,
    get_flashcards,
    get_learningpath,
    get_mcqs,
    get_one_word_questions,
    get_study_material_basic,
    get_study_material_reasoning,
    get_true_false_questions,
    moderate_content,
)
from backend.services.generation_runs import (
    claim_generation_run,
    complete_step,
    create_generation_run,
    get_generation_run,
    list_active_generation_runs,
    mark_step_failed,
    prepare_generation_retry,
    recoverable_generation_run_ids,
    request_generation_cancellation,
    serialize_generation_run,
    update_generation_run,
    utcnow,
)

try:
    from langgraph.graph import END, StateGraph
except ImportError:  # pragma: no cover - exercised only before optional dependencies sync
    END = None
    StateGraph = None


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="generation")


def refund_generation_quota(job_id):
    """Refund the quota slot consumed at submission, at most once per run.

    Called on terminal failure or cancellation so transient errors do not
    permanently consume a user's daily generation quota.
    """
    marked = mongo.db.generation_runs.update_one(
        {"_id": job_id, "quota_refunded": {"$ne": True}},
        {"$set": {"quota_refunded": True}},
    )
    if marked.modified_count == 0:
        return  # already refunded for this run
    run = mongo.db.generation_runs.find_one({"_id": job_id}, {"user_id": 1, "mode": 1})
    if not run or not run.get("user_id"):
        return
    counter = "deep_rate_limit" if run.get("mode") == "Pro Reasoning" else "rate_limit"
    mongo.db.users.update_one(
        {"_id": run["user_id"], counter: {"$gt": 0}},
        {"$inc": {counter: -1}},
    )


class WorkflowState(TypedDict, total=False):
    job_id: str
    cached: bool


class GenerationCancelled(Exception):
    pass


class GenerationStepFailed(Exception):
    def __init__(self, step: str, cause: Exception):
        super().__init__(str(cause))
        self.step = step
        self.cause = cause


def model_for_generation_mode(app, mode):
    if mode == "Pro Reasoning":
        return app.config.get("GEMINI_DEEP_FOCUS_MODEL_NAME") or "gemini-2.5-pro"
    return None


def enqueue_generation_job(
    app,
    user_id,
    topic,
    difflvl,
    mode,
    force_new=False,
    regenerated_from=None,
    version=1,
    original_topic=None,
    adaptive_source=None,
    source_grounding=None,
    idempotency_key=None,
):
    try:
        user_doc = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    except (InvalidId, TypeError):
        user_doc = None
    learner_context = learner_context_snapshot(user_doc)
    run, created = create_generation_run(
        user_id=user_id,
        topic=topic,
        original_topic=original_topic or topic,
        difficulty_level=difflvl,
        mode=mode or "Basic",
        model_name=model_for_generation_mode(app, mode or "Basic"),
        force_new=force_new,
        regenerated_from=regenerated_from,
        version=version,
        adaptive_source=adaptive_source,
        source_grounding=source_grounding,
        learner_context=learner_context,
        idempotency_key=idempotency_key or os.urandom(16).hex(),
    )
    if created:
        _dispatch_generation_run(app, run["_id"])
    result = serialize_generation_run(run)
    result["deduplicated"] = not created
    return result


def get_generation_job(job_id, user_id=None):
    run = get_generation_run(job_id, user_id)
    return serialize_generation_run(run) if run else None


def get_active_generation_jobs(user_id):
    return [serialize_generation_run(run) for run in list_active_generation_runs(user_id)]


def cancel_generation_job(job_id, user_id):
    run = request_generation_cancellation(job_id, user_id)
    return serialize_generation_run(run) if run else None


def retry_generation_job(app, job_id, user_id):
    run = prepare_generation_retry(job_id, user_id)
    if not run:
        return None
    # A retry re-consumes the quota slot that was refunded on failure,
    # so the next terminal failure can be refunded again.
    if run.get("quota_refunded"):
        mongo.db.generation_runs.update_one(
            {"_id": job_id}, {"$set": {"quota_refunded": False}}
        )
    _dispatch_generation_run(app, job_id)
    return serialize_generation_run(run)


def resume_incomplete_generation_jobs(app):
    for run_id in recoverable_generation_run_ids():
        _dispatch_generation_run(app, run_id)


def run_generation_job(job_id):
    """RQ entry point. The worker creates its own application context."""
    from backend import create_app

    app = create_app(resume_generation_runs=False)
    _run_generation_job(app, job_id)


def _dispatch_generation_run(app, job_id):
    worker_mode = str(app.config.get("GENERATION_WORKER_MODE", "local")).lower()
    redis_url = app.config.get("REDIS_URL")
    if worker_mode in {"rq", "auto"} and redis_url:
        try:
            from redis import Redis
            from rq import Queue

            queue = Queue(
                app.config.get("GENERATION_QUEUE_NAME", "generation"),
                connection=Redis.from_url(redis_url),
            )
            run = get_generation_run(job_id) or {}
            queue.enqueue(
                "backend.services.generation_jobs.run_generation_job",
                job_id,
                job_id=f"generation:{job_id}:{run.get('attempt', 1)}",
                result_ttl=86400,
                failure_ttl=86400,
            )
            return
        except Exception as exc:
            if worker_mode == "rq":
                update_generation_run(
                    job_id,
                    status="failed",
                    error={
                        "code": "worker_unavailable",
                        "message": "Course creation is temporarily unavailable.",
                        "retryable": True,
                        "step": "queued",
                    },
                    message="Could not start course creation.",
                )
                app.logger.error("Could not enqueue RQ generation job: %s", exc)
                return
            app.logger.warning("RQ unavailable; using local generation worker: %s", exc)

    _executor.submit(_run_generation_job, app, job_id)


def _run_generation_job(app, job_id):
    with app.app_context():
        owner = f"{socket.gethostname()}:{os.getpid()}"
        lease_seconds = int(app.config.get("GENERATION_LEASE_SECONDS", 900))
        run = claim_generation_run(job_id, owner, lease_seconds)
        if not run:
            return
        try:
            GenerationOrchestrator(app, job_id).run()
        except GenerationCancelled:
            update_generation_run(
                job_id,
                status="cancelled",
                message="Course creation cancelled.",
                completed_at=utcnow(),
                lease_owner=None,
                lease_expires_at=None,
            )
            refund_generation_quota(job_id)
        except GenerationStepFailed as exc:
            app.logger.warning(
                "Generation run %s step %s failed: %s",
                job_id,
                exc.step,
                exc.cause,
            )
            mark_step_failed(job_id, exc.step)
            update_generation_run(
                job_id,
                status="failed",
                message=f"Course creation paused while preparing {_public_step_label(exc.step)}.",
                error={
                    "code": "generation_step_failed",
                    "message": _public_step_error(exc.step),
                    "retryable": exc.step not in {"safety", "user"},
                    "step": exc.step,
                },
                completed_at=utcnow(),
                lease_owner=None,
                lease_expires_at=None,
            )
            refund_generation_quota(job_id)
        except Exception as exc:
            app.logger.exception("Generation run %s failed", job_id)
            update_generation_run(
                job_id,
                status="failed",
                message="Course creation did not finish.",
                error={
                    "code": "generation_failed",
                    "message": "Your course could not be completed. Please try again.",
                    "retryable": True,
                    "step": _current_stage(job_id),
                },
                completed_at=utcnow(),
                lease_owner=None,
                lease_expires_at=None,
            )
            refund_generation_quota(job_id)


class GenerationOrchestrator:
    """Checkpointed generation graph; Mongo is the durable source of truth."""

    def __init__(self, app, job_id: str):
        self.app = app
        self.job_id = job_id

    def run(self):
        if StateGraph is None:
            state = self.prepare({"job_id": self.job_id})
            if state.get("cached"):
                return
            self.plan_curriculum(state)
            self.plan_knowledge_packs(state)
            self.generate_artifacts(state)
            self.save_session(state)
            return

        graph = StateGraph(WorkflowState)
        graph.add_node("prepare", self.prepare)
        graph.add_node("curriculum", self.plan_curriculum)
        graph.add_node("knowledge", self.plan_knowledge_packs)
        graph.add_node("artifacts", self.generate_artifacts)
        graph.add_node("save", self.save_session)
        graph.set_entry_point("prepare")
        graph.add_conditional_edges(
            "prepare",
            lambda state: "done" if state.get("cached") else "continue",
            {"done": END, "continue": "curriculum"},
        )
        graph.add_edge("curriculum", "knowledge")
        graph.add_edge("knowledge", "artifacts")
        graph.add_edge("artifacts", "save")
        graph.add_edge("save", END)
        graph.compile().invoke({"job_id": self.job_id})

    def prepare(self, state: WorkflowState) -> WorkflowState:
        job = self._job()
        self._check_cancelled(job)
        update_generation_run(
            self.job_id,
            status="repairing" if int(job.get("attempt", 1)) > 1 else "running",
            stage="safety",
            progress=max(5, int(job.get("progress", 0))),
            message="Reviewing your topic.",
        )
        if "safety" not in job.get("completed_steps", []):
            if not moderate_content(job["topic"]):
                raise GenerationStepFailed(
                    "safety", ValueError("Topic is invalid or not suitable for generation.")
                )
            complete_step(self.job_id, "safety")

        user_doc = mongo.db.users.find_one({"_id": job["user_id"]})
        if not user_doc:
            raise GenerationStepFailed("user", ValueError("User not found."))

        update_generation_run(
            self.job_id,
            stage="cache",
            progress=max(10, int(job.get("progress", 0))),
            message="Checking your saved courses.",
        )
        if not job.get("force_new"):
            cached = find_cached_session(
                str(job["user_id"]),
                job["topic"],
                job["difficulty_level"],
                job["mode"],
                personalization_profile=job.get("learner_context"),
            )
            if cached:
                complete_step(self.job_id, "cache")
                update_generation_run(
                    self.job_id,
                    status="completed",
                    stage="completed",
                    progress=100,
                    message="Found a matching saved course.",
                    session_id=str(cached["_id"]),
                    completed_at=utcnow(),
                    lease_owner=None,
                    lease_expires_at=None,
                )
                return {**state, "cached": True}
        complete_step(self.job_id, "cache")
        return {**state, "cached": False}

    def plan_curriculum(self, state: WorkflowState) -> WorkflowState:
        job = self._job()
        self._check_cancelled(job)
        if job.get("checkpoints", {}).get("curriculum"):
            return state
        update_generation_run(
            self.job_id,
            stage="curriculum",
            progress=max(15, int(job.get("progress", 0))),
            message="Building your learning path.",
        )
        try:
            curriculum = plan_curriculum(
                job["topic"],
                job["difficulty_level"],
                job.get("model_name"),
                source_context=(job.get("source_grounding") or {}).get("context"),
                learner_context=learner_context_instruction(job.get("learner_context")),
            )
        except Exception as exc:
            raise GenerationStepFailed("curriculum", exc) from exc
        complete_step(
            self.job_id, "curriculum", curriculum.model_dump(mode="json")
        )
        update_generation_run(self.job_id, progress=24)
        return state

    def generate_artifacts(self, state: WorkflowState) -> WorkflowState:
        job = self._job()
        self._check_cancelled(job)
        curriculum = Curriculum.model_validate(job["checkpoints"]["curriculum"])
        knowledge_packs = CourseKnowledgePacks.model_validate(
            job["checkpoints"]["knowledge_packs"]
        )
        _generate_modules(self.app, job, curriculum, knowledge_packs, self.job_id)
        return state

    def plan_knowledge_packs(self, state: WorkflowState) -> WorkflowState:
        job = self._job()
        self._check_cancelled(job)
        if job.get("checkpoints", {}).get("knowledge_packs"):
            return state
        update_generation_run(
            self.job_id,
            stage="knowledge",
            progress=max(25, int(job.get("progress", 0))),
            message="Connecting every part of your course.",
        )
        curriculum = Curriculum.model_validate(job["checkpoints"]["curriculum"])
        grounding = job.get("source_grounding") or {}
        try:
            packs = build_knowledge_packs(
                curriculum,
                job.get("model_name"),
                source_context=grounding.get("context"),
                source_references=list(grounding.get("source_ids") or []),
            )
        except Exception as exc:
            raise GenerationStepFailed("knowledge_packs", exc) from exc
        complete_step(
            self.job_id, "knowledge_packs", packs.model_dump(mode="json")
        )
        update_generation_run(self.job_id, progress=32)
        return state

    def save_session(self, state: WorkflowState) -> WorkflowState:
        job = self._job()
        self._check_cancelled(job)
        update_generation_run(
            self.job_id,
            status="saving",
            stage="saving",
            progress=94,
            message="Saving your course.",
        )
        curriculum = Curriculum.model_validate(job["checkpoints"]["curriculum"])
        knowledge_packs = CourseKnowledgePacks.model_validate(
            job["checkpoints"]["knowledge_packs"]
        )
        generated = {
            name: job.get("checkpoints", {}).get(f"artifact:{name}")
            for name in ARTIFACT_TASK_NAMES
        }
        missing = [name for name, value in generated.items() if value is None]
        if missing:
            raise GenerationStepFailed(
                missing[0], RuntimeError("A required generation checkpoint is missing.")
            )
        _apply_generation_lineage(generated, job)

        existing = mongo.db.sessions.find_one({"generation_run_id": self.job_id})
        if existing:
            session_id = str(existing["_id"])
        else:
            now = utcnow()
            new_session = {
                "_id": job["target_session_id"],
                "generation_run_id": self.job_id,
                "user_id": job["user_id"],
                "topic": job["topic"],
                "original_topic": job.get("original_topic") or job["topic"],
                "normalized_topic": normalize_topic(job["topic"]),
                "difficulty_level": (job["difficulty_level"] or "").strip().lower(),
                "generation_mode": job["mode"],
                "version": job.get("version") or 1,
                "curriculum_id": curriculum.curriculum_id,
                "curriculum": curriculum.model_dump(mode="json"),
                "knowledge_pack_version": knowledge_packs.prompt_version,
                "module_knowledge_packs": knowledge_packs.model_dump(mode="json")["packs"],
                "subtopics": curriculum.subtopics,
                "course_content": generated["course_content"],
                "study_materials": generated["study_materials"],
                "flashcards": generated["flashcards"],
                "mcqs": generated["mcqs"],
                "true_false": generated["true_false"],
                "oneword": generated["oneword"],
                "learningpath": generated["learningpath"],
                "additionalresources": generated["additionalresources"],
                "source_ids": [ObjectId(item) for item in (job.get("source_grounding") or {}).get("source_ids", [])],
                "source_lineage": (job.get("source_grounding") or {}).get("sources", []),
                "source_citations": (job.get("source_grounding") or {}).get("citations", []),
                "personalization_profile": job.get("learner_context"),
                "created_at": now,
            }
            _apply_session_lineage(new_session, job)
            try:
                mongo.db.sessions.insert_one(new_session)
            except DuplicateKeyError:
                existing = mongo.db.sessions.find_one(
                    {"generation_run_id": self.job_id}
                )
                if not existing:
                    raise
                new_session = existing
            session_id = str(new_session["_id"])

        complete_step(self.job_id, "saving")
        update_generation_run(
            self.job_id,
            status="completed",
            stage="completed",
            progress=100,
            message="Course created successfully.",
            session_id=session_id,
            completed_at=utcnow(),
            lease_owner=None,
            lease_expires_at=None,
        )
        return state

    def _job(self) -> dict[str, Any]:
        job = get_generation_run(self.job_id)
        if not job:
            raise RuntimeError("Generation run no longer exists.")
        return job

    @staticmethod
    def _check_cancelled(job):
        if job.get("cancel_requested") or job.get("status") == "cancelled":
            raise GenerationCancelled()


ARTIFACT_TASK_NAMES = (
    "study_materials",
    "flashcards",
    "mcqs",
    "true_false",
    "oneword",
    "course_content",
    "learningpath",
    "additionalresources",
)


def _generate_modules(app, job, curriculum, knowledge_packs, job_id):
    subtopics = curriculum.subtopics
    grounding_context = (job.get("source_grounding") or {}).get("context")
    grounded_topic = (
        f"{job['topic']}\n\n{grounding_context}"
        if grounding_context
        else job["topic"]
    )
    packs_by_module = {pack.module_id: pack for pack in knowledge_packs.packs}

    def with_context(fn, *args):
        with app.app_context():
            return fn(*args)

    def study_materials():
        if job["mode"] == "Pro Reasoning":
            materials = with_context(
                get_study_material_reasoning,
                job["topic"],
                subtopics,
                job["difficulty_level"],
                job.get("model_name"),
                knowledge_packs,
            )
        else:
            materials = with_context(
                get_study_material_basic,
                job["topic"],
                subtopics,
                job.get("model_name"),
                knowledge_packs,
            )
        for index, material in enumerate(materials):
            if not isinstance(material, dict) or index >= len(curriculum.modules):
                continue
            module = curriculum.modules[index]
            material.update(
                {
                    "curriculum_id": curriculum.curriculum_id,
                    "module_id": module.module_id,
                    "concept_ids": [concept.concept_id for concept in module.concepts],
                    "objective_ids": [
                        objective.objective_id for objective in module.learning_objectives
                    ],
                    "difficulty": curriculum.difficulty.value,
                    "generation_kind": "standard",
                    "knowledge_pack_id": packs_by_module[module.module_id].knowledge_pack_id,
                    "knowledge_pack_version": knowledge_packs.prompt_version,
                    "grounding_refs": list(packs_by_module[module.module_id].source_references),
                    "prompt_version": "study-material-pack-v1",
                    "validation_status": "validated",
                }
            )
        return materials

    tasks = {
        "study_materials": (
            study_materials,
            "materials",
            "Preparing Study Materials.",
        ),
        "flashcards": (
            lambda: with_context(
                get_flashcards,
                job["topic"],
                job["difficulty_level"],
                job.get("model_name"),
                curriculum,
                knowledge_packs,
            ),
            "practice",
            "Preparing Flashcards.",
        ),
        "mcqs": (
            lambda: with_context(
                get_mcqs,
                job["topic"],
                job["difficulty_level"],
                job.get("model_name"),
                curriculum,
                knowledge_packs,
            ),
            "practice",
            "Preparing Assessments.",
        ),
        "true_false": (
            lambda: with_context(
                get_true_false_questions,
                job["topic"],
                job["difficulty_level"],
                job.get("model_name"),
                curriculum,
                knowledge_packs,
            ),
            "practice",
            "Preparing Assessments.",
        ),
        "oneword": (
            lambda: with_context(
                get_one_word_questions,
                job["topic"],
                job["difficulty_level"],
                job.get("model_name"),
                curriculum,
                knowledge_packs,
            ),
            "practice",
            "Preparing Assessments.",
        ),
        "course_content": (
            lambda: with_context(
                get_course_content,
                job["topic"],
                job["difficulty_level"],
                job.get("model_name"),
                curriculum,
                knowledge_packs,
            ),
            "videos",
            "Preparing Video Lectures.",
        ),
        "learningpath": (
            lambda: with_context(
                get_learningpath,
                grounded_topic,
                job["difficulty_level"],
                job.get("model_name"),
            ),
            "learning_path",
            "Building your Learning Path.",
        ),
        "additionalresources": (
            lambda: with_context(get_additional_resources_links, job["topic"]),
            "resources",
            "Preparing Additional Resources.",
        ),
    }

    completed = set(job.get("completed_steps", []))
    pending = {
        name: task
        for name, task in tasks.items()
        if f"artifact:{name}" not in completed
        or job.get("checkpoints", {}).get(f"artifact:{name}") is None
    }
    if not pending:
        return

    total = len(tasks)
    done_count = total - len(pending)
    errors: list[tuple[str, Exception]] = []
    with ThreadPoolExecutor(max_workers=4) as module_executor:
        futures = {
            module_executor.submit(fn): (name, stage, message)
            for name, (fn, stage, message) in pending.items()
        }
        for future in as_completed(futures):
            name, stage, message = futures[future]
            latest = get_generation_run(job_id)
            if latest and latest.get("cancel_requested"):
                raise GenerationCancelled()
            try:
                result = future.result()
                _validate_artifact_alignment(name, result, curriculum, knowledge_packs)
                complete_step(job_id, f"artifact:{name}", result)
                done_count += 1
                progress = 32 + int((done_count / total) * 58)
                update_generation_run(
                    job_id,
                    stage=stage,
                    progress=progress,
                    message=message,
                )
            except Exception as exc:
                mark_step_failed(job_id, f"artifact:{name}")
                errors.append((f"artifact:{name}", exc))

    if errors:
        step, error = errors[0]
        raise GenerationStepFailed(step, error)


def _validate_artifact_alignment(name, result, curriculum, knowledge_packs):
    if name not in {"study_materials", "flashcards", "mcqs", "true_false", "oneword", "course_content"}:
        return
    if not isinstance(result, list):
        raise ValueError(f"{name} did not return a list.")

    modules = {module.module_id: module for module in curriculum.modules}
    packs = {pack.module_id: pack for pack in knowledge_packs.packs}
    counts = {module_id: 0 for module_id in modules}
    links = set()
    prompts = set()
    for item in result:
        if not isinstance(item, dict):
            raise ValueError(f"{name} contains an invalid item.")
        module_id = item.get("module_id")
        if module_id not in modules:
            raise ValueError(f"{name} contains an unknown module reference.")
        counts[module_id] += 1
        module = modules[module_id]
        valid_concepts = {concept.concept_id for concept in module.concepts}
        valid_objectives = {objective.objective_id for objective in module.learning_objectives}
        if not set(item.get("concept_ids") or []).issubset(valid_concepts):
            raise ValueError(f"{name} contains a concept from the wrong module.")
        if not set(item.get("objective_ids") or []).issubset(valid_objectives):
            raise ValueError(f"{name} contains an objective from the wrong module.")
        if item.get("knowledge_pack_id") != packs[module_id].knowledge_pack_id:
            raise ValueError(f"{name} is not linked to its module knowledge pack.")
        if name in {"flashcards", "mcqs", "true_false", "oneword"}:
            prompt = " ".join(str(item.get("question") or "").casefold().split())
            if not prompt or prompt in prompts:
                raise ValueError(f"{name} contains a missing or duplicate question.")
            prompts.add(prompt)
        if name == "course_content":
            link = item.get("link") or item.get("url")
            if not link or link in links:
                raise ValueError("Video Lectures must be unique across modules.")
            links.add(link)
            if float(item.get("video_relevance_score") or 0) <= 0:
                raise ValueError("A Video Lecture did not pass relevance ranking.")

    expected = 2 if name in {"flashcards", "mcqs", "true_false", "oneword"} else 1
    if any(count != expected for count in counts.values()):
        label = "at least one" if name == "course_content" else str(expected)
        raise ValueError(f"{name} must contain {label} aligned item(s) per module.")


def _apply_generation_lineage(generated, job):
    generation_kind = (
        "source_grounded"
        if job.get("source_grounding")
        else "weak_topic_remediation"
        if job.get("adaptive_source")
        else "standard"
    )
    source_submission_id = None
    if job.get("adaptive_source"):
        source_submission_id = (
            str(job["adaptive_source"].get("assessment_submission_id") or "") or None
        )
    adaptive_source = job.get("adaptive_source") or {}

    source_grounding = job.get("source_grounding") or {}
    citations = list(source_grounding.get("citations") or [])
    source_ids = list(source_grounding.get("source_ids") or [])
    for field in ("study_materials", "flashcards", "mcqs", "true_false", "oneword", "course_content"):
        for item in generated.get(field, []):
            if not isinstance(item, dict):
                continue
            item["generation_kind"] = generation_kind
            if source_ids:
                item["source_ids"] = source_ids
                item["source_citations"] = citations
            if source_submission_id:
                item["source_assessment_submission_id"] = source_submission_id
            if adaptive_source.get("decision_id"):
                item["source_adaptation_decision_id"] = adaptive_source["decision_id"]
            if adaptive_source.get("adaptive_action"):
                item["adaptive_action"] = adaptive_source["adaptive_action"]
            if adaptive_source.get("target_concept_ids"):
                item["target_concept_ids"] = list(adaptive_source["target_concept_ids"])
            if adaptive_source.get("target_objective_ids"):
                item["target_objective_ids"] = list(adaptive_source["target_objective_ids"])


def _apply_session_lineage(new_session, job):
    if job.get("regenerated_from"):
        try:
            new_session["regenerated_from"] = ObjectId(job["regenerated_from"])
        except (InvalidId, TypeError):
            new_session["regenerated_from"] = job["regenerated_from"]
    if job.get("adaptive_source"):
        adaptive_source = job["adaptive_source"]
        new_session.update(
            {
                "generation_kind": "adaptive",
                "adaptive_from_session": adaptive_source.get("session_id"),
                "adaptive_from_topic": adaptive_source.get("topic"),
                "assessment_submission_id": adaptive_source.get(
                    "assessment_submission_id"
                ),
                "source_adaptation_decision_id": adaptive_source.get("decision_id"),
                "adaptive_action": adaptive_source.get("adaptive_action"),
                "target_concept_ids": list(adaptive_source.get("target_concept_ids") or []),
                "target_objective_ids": list(adaptive_source.get("target_objective_ids") or []),
            }
        )
    if job.get("source_grounding"):
        new_session["generation_kind"] = "source_grounded"
        new_session["grounding_version"] = (
            job["source_grounding"].get("retrieval_version")
        )


def _current_stage(job_id):
    job = get_generation_run(job_id)
    return job.get("stage") if job else None


def _public_step_error(step):
    if step == "safety":
        return "This topic could not pass the learning-content safety check."
    if step == "user":
        return "Your account could not be loaded while creating this course."
    return "This part of your course did not finish. Retry will keep completed content and continue from here."


def _public_step_label(step):
    return {
        "curriculum": "the Learning Path",
        "study_materials": "Study Materials",
        "course_content": "Video Lectures",
        "flashcards": "Flashcards",
        "mcqs": "Assessments",
        "true_false": "Assessments",
        "oneword": "Assessments",
        "learningpath": "the Learning Path",
        "additionalresources": "Additional Resources",
        "saving": "the course",
    }.get(step, "the course")
