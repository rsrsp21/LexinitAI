"""Final assessment: the check that turns "finished the course" into "knows it".

It unlocks once every module is passed, mixes all modules and question types,
uses questions the learner has never seen, and leans toward the concepts where
their mastery is lowest. Passing it is required for the course badge. A failed
attempt produces a review plan and can be retaken after a cooling-off period.

Questions and answers live only in the attempt record on the server.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import random
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument

from backend.lexinit.api.errors import ApiError
from backend.lexinit.domain.assessment import AssessmentSubmissionError, grade_assessment
from backend.lexinit.domain.assessment.grading import ASSESSMENT_FIELDS
from backend.lexinit.domain.mastery.calculator import mastery_band, retention
from backend.lexinit.schemas.assessment import AssessmentType
from backend.lexinit.schemas.generated_content import MCQDraft, OneWordDraft, TrueFalseDraft
from backend.lexinit.schemas.generation import Difficulty
from backend.lexinit.services.adaptive import AdaptiveLearningService
from backend.lexinit.services.curriculum import StructuredGenerator
from backend.lexinit.services.learner_context import learner_context_instruction
from backend.lexinit.services.question_quality import verify_answer_keys


FINAL_PROMPT_VERSION = "final-v1"
FINAL_PASS_PERCENT = 70
FINAL_MCQ_COUNT = 5
FINAL_TRUE_FALSE_COUNT = 4
FINAL_ONE_WORD_COUNT = 3
FINAL_QUESTION_COUNT = FINAL_MCQ_COUNT + FINAL_TRUE_FALSE_COUNT + FINAL_ONE_WORD_COUNT
FINAL_MIN_QUESTIONS = 9
FINAL_ATTEMPT_WINDOW = datetime.timedelta(hours=3)
FINAL_RETRY_COOLDOWN = datetime.timedelta(hours=24)


class FinalSetDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mcqs: list[MCQDraft] = Field(min_length=FINAL_MCQ_COUNT, max_length=FINAL_MCQ_COUNT)
    true_false: list[TrueFalseDraft] = Field(
        min_length=FINAL_TRUE_FALSE_COUNT, max_length=FINAL_TRUE_FALSE_COUNT
    )
    one_word: list[OneWordDraft] = Field(
        min_length=FINAL_ONE_WORD_COUNT, max_length=FINAL_ONE_WORD_COUNT
    )


def utcnow() -> datetime.datetime:
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def _aware(value):
    if isinstance(value, datetime.datetime) and value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value


def _iso(value):
    value = _aware(value)
    return value.isoformat() if isinstance(value, datetime.datetime) else None


def _stem_key(value: str) -> str:
    return " ".join(str(value).casefold().split())


def final_assessment_state(db, user_id: ObjectId, session_id: Any) -> dict[str, Any]:
    """Summary of a learner's final assessment for one course."""
    now = utcnow()
    attempts = list(
        db.final_assessments.find(
            {"user_id": user_id, "session_id": session_id},
            {"status": 1, "percent": 1, "passed": 1, "score": 1, "total": 1, "completed_at": 1, "expires_at": 1},
        ).sort("created_at", 1)
    )
    completed = [item for item in attempts if item.get("status") == "completed"]
    active = next(
        (
            item
            for item in reversed(attempts)
            if item.get("status") == "active" and _aware(item.get("expires_at")) > now
        ),
        None,
    )
    passed = any(item.get("passed") for item in completed)
    last = completed[-1] if completed else None
    retry_at = None
    if last and not passed:
        candidate = _aware(last["completed_at"]) + FINAL_RETRY_COOLDOWN
        if candidate > now:
            retry_at = candidate
    return {
        "passed": passed,
        "attempts": len(completed),
        "best_percent": max((int(item.get("percent") or 0) for item in completed), default=None),
        "pass_percent": FINAL_PASS_PERCENT,
        "question_count": FINAL_QUESTION_COUNT,
        "active_final_id": active["_id"] if active else None,
        "last_final_id": last["_id"] if last else None,
        "last_percent": int(last.get("percent") or 0) if last else None,
        "retry_available_at": _iso(retry_at),
    }


class FinalAssessmentService:
    def __init__(
        self,
        *,
        db,
        generator: StructuredGenerator,
        adaptive_service: AdaptiveLearningService,
        course_progress,
        verifier: StructuredGenerator | None = None,
    ) -> None:
        self._db = db
        self._generator = generator
        # Checking answer keys is a simpler task than writing the questions,
        # so it can run on a faster model.
        self._verifier = verifier or generator
        self._adaptive = adaptive_service
        self._course_progress = course_progress

    # ------------------------------------------------------------------ status

    def status(self, *, user_id: ObjectId, session_data: dict[str, Any]) -> dict[str, Any]:
        course = self._course_progress.course(user_id, session_data)
        return self._status_from_course(course)

    @staticmethod
    def _status_from_course(course: dict[str, Any]) -> dict[str, Any]:
        final = dict(course.get("final_assessment") or {})
        final["modules_remaining"] = [
            {"module_id": module["module_id"], "title": module["title"]}
            for module in course["modules"]
            if not module.get("passed")
        ]
        return final

    # ------------------------------------------------------------------- start

    def start(self, *, user_id: ObjectId, session_data: dict[str, Any]) -> dict[str, Any]:
        course = self._course_progress.course(user_id, session_data)
        final = course.get("final_assessment") or {}
        if not final.get("required"):
            raise ApiError(
                "This course has no final assessment.",
                status_code=409,
                code="final_not_available",
            )
        if final.get("active_final_id"):
            return self.get(user_id=user_id, final_id=final["active_final_id"])
        if final.get("passed"):
            raise ApiError(
                "You have already passed the final assessment.",
                status_code=409,
                code="final_already_passed",
            )
        if final["state"] == "locked":
            raise ApiError(
                "Pass every module's assessments to unlock the final assessment.",
                status_code=409,
                code="final_locked",
            )
        if final.get("retry_available_at"):
            raise ApiError(
                "Review what you missed first. You can retake the final assessment later.",
                status_code=409,
                code="final_cooldown",
                details={"retry_available_at": final["retry_available_at"]},
            )

        questions = self._generate_questions(user_id, session_data)
        verified = verify_answer_keys(self._verifier, questions)
        if len(verified) >= FINAL_MIN_QUESTIONS:
            questions = verified
        now = utcnow()
        final_id = f"final_{hashlib.sha256(f'{user_id}|{session_data['_id']}|{now.isoformat()}'.encode()).hexdigest()[:28]}"
        random.Random(final_id).shuffle(questions)
        document = {
            "_id": final_id,
            "user_id": user_id,
            "session_id": session_data["_id"],
            "source_topic": str(session_data.get("topic") or "Untitled course"),
            "status": "active",
            "questions": questions,
            "prompt_version": FINAL_PROMPT_VERSION,
            "created_at": now,
            "expires_at": now + FINAL_ATTEMPT_WINDOW,
        }
        self._db.final_assessments.insert_one(document)
        return self._public(document)

    def _generate_questions(
        self, user_id: ObjectId, session_data: dict[str, Any], *, correction: str = ""
    ) -> list[dict[str, Any]]:
        modules = list((session_data.get("curriculum") or {}).get("modules") or [])
        concept_module = {
            concept["concept_id"]: module["module_id"]
            for module in modules
            for concept in module.get("concepts") or []
            if concept.get("concept_id")
        }
        mastery = self._current_mastery(user_id, list(concept_module))
        packs = {
            item.get("module_id"): item
            for item in session_data.get("module_knowledge_packs") or []
            if isinstance(item, dict)
        }
        payload = {
            "topic": session_data.get("topic"),
            "difficulty": session_data.get("difficulty_level"),
            "modules": [
                {
                    "module_id": module.get("module_id"),
                    "title": module.get("title"),
                    "concepts": [
                        {
                            "concept_id": concept.get("concept_id"),
                            "name": concept.get("name"),
                            "learner_mastery_percent": (
                                round(mastery[concept["concept_id"]] * 100)
                                if concept.get("concept_id") in mastery
                                else None
                            ),
                        }
                        for concept in module.get("concepts") or []
                    ],
                    "objectives": [
                        {"objective_id": item.get("objective_id"), "description": item.get("description")}
                        for item in module.get("learning_objectives") or []
                    ],
                    "knowledge": {
                        key: (packs.get(module.get("module_id")) or {}).get(key)
                        for key in ("definitions", "important_facts", "common_mistakes")
                        if (packs.get(module.get("module_id")) or {}).get(key)
                    },
                }
                for module in modules
            ],
        }
        # Earlier final attempts first: those are the likeliest to be repeated.
        seen = [
            str(question.get("question") or "")
            for previous in self._db.final_assessments.find(
                {"user_id": user_id, "session_id": session_data["_id"]}, {"questions.question": 1}
            ).sort("created_at", -1)
            for question in previous.get("questions") or []
        ]
        seen += [
            str(item.get("question") or "")
            for fields in ASSESSMENT_FIELDS.values()
            for field in fields
            for item in session_data.get(field) or []
            if isinstance(item, dict)
        ]
        learner = learner_context_instruction(session_data.get("personalization_profile")) or ""
        prompt = (
            "Write the final assessment for a course. It decides whether the learner earns the "
            "course badge, so it must test understanding across the whole course.\n"
            f"Write exactly {FINAL_MCQ_COUNT} multiple-choice questions (four unique options, one "
            f"correct_option_index, misconceptions for tempting wrong options), {FINAL_TRUE_FALSE_COUNT} "
            f"true/false statements, and {FINAL_ONE_WORD_COUNT} questions answered by exactly one word "
            "or one hyphenated word. Every question needs a concise explanation and must list the "
            "concept_ids it tests, using only ids from the course JSON.\n"
            "Coverage rules: every module must be tested by at least two questions. Give more "
            "questions to concepts with a low learner_mastery_percent, and include at least three "
            "questions that combine ideas from two modules. Prefer application and reasoning over "
            "recalling definitions.\n"
            "The learner has already seen the answers to these questions, so never repeat or "
            "lightly reword them:\n"
            + "\n".join(f"- {stem}" for stem in seen[:90] if stem)
            + correction
            + f"\n\nCOURSE JSON:\n{json.dumps(payload, ensure_ascii=False)[:24000]}\n\n{learner}"
        )
        try:
            draft = self._generator.generate_structured(prompt, FinalSetDraft, temperature=0.4)
        except Exception as exc:
            raise ApiError(
                "The final assessment could not be prepared. Please try again in a moment.",
                status_code=503,
                code="final_unavailable",
            ) from exc

        difficulty = str(session_data.get("difficulty_level") or "medium").lower()
        if difficulty not in {item.value for item in Difficulty}:
            difficulty = Difficulty.MEDIUM.value
        module_ids = [module["module_id"] for module in modules if module.get("module_id")]
        all_concepts = list(concept_module)
        questions: list[dict[str, Any]] = []

        def base(item, assessment_type: AssessmentType, index: int) -> dict[str, Any]:
            concept_ids = [value for value in item.concept_ids if value in concept_module]
            if not concept_ids and module_ids:
                fallback_module = module_ids[index % len(module_ids)]
                concept_ids = [key for key, value in concept_module.items() if value == fallback_module][:2]
            return {
                "question_id": f"final_{assessment_type.value}_{hashlib.sha256(item.question.encode()).hexdigest()[:20]}",
                "type": assessment_type.value,
                "question": item.question.strip(),
                "explanation": item.explanation.strip(),
                "concept_ids": concept_ids or all_concepts[:1],
                "module_id": concept_module.get(concept_ids[0]) if concept_ids else None,
                "difficulty": difficulty,
                "generation_kind": "final",
            }

        for index, item in enumerate(draft.mcqs):
            question = base(item, AssessmentType.MCQ, index)
            question["options"] = [option.strip() for option in item.options]
            question["answer"] = item.correct_option_index
            question["misconception_map"] = {
                chr(ord("A") + entry.option_index): entry.misconception.strip()
                for entry in item.misconceptions
            }
            questions.append(question)
        for index, item in enumerate(draft.true_false):
            question = base(item, AssessmentType.TRUE_FALSE, index)
            question["answer"] = item.answer
            question["misconception_map"] = (
                {str(not item.answer).lower(): item.misconception_if_wrong.strip()}
                if item.misconception_if_wrong
                else {}
            )
            questions.append(question)
        for index, item in enumerate(draft.one_word):
            question = base(item, AssessmentType.ONE_WORD, index)
            question["answer"] = item.answer.strip()
            question["misconception_map"] = (
                {"*": item.misconception_if_wrong.strip()} if item.misconception_if_wrong else {}
            )
            questions.append(question)

        # Never show a question whose answer the learner has already seen.
        known = {_stem_key(stem) for stem in seen}
        fresh = [item for item in questions if _stem_key(item["question"]) not in known]
        counts = {module_id: 0 for module_id in module_ids}
        for item in fresh:
            for module_id in {concept_module[value] for value in item["concept_ids"] if value in concept_module}:
                counts[module_id] += 1
        untested = [
            str(module.get("title")) for module in modules if counts.get(module.get("module_id"), 0) == 0
        ]
        if len(fresh) >= FINAL_MIN_QUESTIONS and not untested:
            return fresh
        if not correction:
            # Regenerating costs a full model call, so it is reserved for a
            # set that is too short or leaves a module untested.
            problems = []
            if len(fresh) < FINAL_MIN_QUESTIONS:
                problems.append("Too many questions repeated ones the learner has seen; write new ones.")
            if untested:
                problems.append("These modules need at least two questions each: " + "; ".join(untested))
            try:
                return self._generate_questions(
                    user_id,
                    session_data,
                    correction="\n\nREQUIRED CORRECTION: " + " ".join(problems),
                )
            except ApiError:
                pass
        if len(fresh) >= FINAL_MIN_QUESTIONS:
            questions = fresh
        return questions

    def _current_mastery(self, user_id: ObjectId, concept_ids: list[str]) -> dict[str, float]:
        now = utcnow()
        result = {}
        for record in self._db.concept_mastery.find(
            {"user_id": user_id, "concept_id": {"$in": concept_ids}}
        ):
            result[record["concept_id"]] = float(record.get("mastery_probability") or 0) * retention(
                record["last_practiced_at"], record["next_review_at"], now
            )
        return result

    # --------------------------------------------------------------------- get

    def get(self, *, user_id: ObjectId, final_id: str) -> dict[str, Any]:
        return self._public(self._owned(user_id, final_id))

    def _owned(self, user_id: ObjectId, final_id: str) -> dict[str, Any]:
        document = self._db.final_assessments.find_one({"_id": final_id, "user_id": user_id})
        if not document:
            raise ApiError("Final assessment not found.", status_code=404, code="final_not_found")
        return document

    def _public(self, document: dict[str, Any]) -> dict[str, Any]:
        completed = document.get("status") == "completed"
        payload = {
            "final_id": document["_id"],
            "session_id": str(document["session_id"]),
            "source_topic": document.get("source_topic") or "Untitled course",
            "status": document["status"],
            "pass_percent": FINAL_PASS_PERCENT,
            "expires_at": _iso(document.get("expires_at")),
            "questions": [
                {
                    "index": index,
                    "type": question["type"],
                    "question": question["question"],
                    "options": list(question.get("options") or []),
                }
                for index, question in enumerate(document["questions"])
            ],
        }
        if completed:
            payload["result"] = document.get("result")
        return payload

    # ------------------------------------------------------------------ submit

    def submit(self, *, user_id: ObjectId, final_id: str, answers: list[Any], session_data_loader) -> dict[str, Any]:
        document = self._owned(user_id, final_id)
        if document["status"] == "completed":
            return self._public(document)
        now = utcnow()
        if _aware(document["expires_at"]) <= now:
            self._db.final_assessments.update_one(
                {"_id": final_id, "status": "active"}, {"$set": {"status": "expired"}}
            )
            raise ApiError(
                "This final assessment expired. Start a new one.",
                status_code=410,
                code="final_expired",
            )
        questions = document["questions"]
        if not isinstance(answers, list) or len(answers) != len(questions):
            raise ApiError("Answer every question before submitting.", code="final_incomplete")

        graded = []
        for index, (question, answer) in enumerate(zip(questions, answers)):
            assessment_type = AssessmentType(question["type"])
            try:
                grading = grade_assessment(assessment_type, [question], [answer])
            except AssessmentSubmissionError as exc:
                raise ApiError(
                    f"Question {index + 1} needs a valid answer.",
                    code="final_invalid_answer",
                ) from exc
            graded.append((assessment_type, grading))

        claimed = self._db.final_assessments.find_one_and_update(
            {"_id": final_id, "user_id": user_id, "status": "active"},
            {"$set": {"status": "grading", "answers": list(answers)}},
            return_document=ReturnDocument.AFTER,
        )
        if not claimed:
            return self._public(self._owned(user_id, final_id))

        session_data = session_data_loader(document["session_id"]) or {}
        concept_names = {
            concept["concept_id"]: str(concept.get("name") or "")
            for module in (session_data.get("curriculum") or {}).get("modules") or []
            for concept in module.get("concepts") or []
            if concept.get("concept_id")
        }
        score = 0
        review = []
        concept_stats: dict[str, dict[str, int]] = {}
        for index, (question, (assessment_type, grading)) in enumerate(zip(questions, graded)):
            feedback = grading.feedback[0]
            snapshot = grading.question_snapshots[0]
            score += 1 if feedback.correct else 0
            for concept_id in question.get("concept_ids") or []:
                stats = concept_stats.setdefault(concept_id, {"asked": 0, "missed": 0})
                stats["asked"] += 1
                stats["missed"] += 0 if feedback.correct else 1
            review.append(
                {
                    "index": index,
                    "type": assessment_type.value,
                    "question": question["question"],
                    "options": list(question.get("options") or []),
                    "selected_answer": snapshot.selected_answer,
                    "selected_option": snapshot.selected_option,
                    "correct": feedback.correct,
                    "correct_answer": feedback.correct_answer,
                    "explanation": feedback.explanation,
                    "concept_ids": list(question.get("concept_ids") or []),
                }
            )
            try:
                self._adaptive.record_assessment(
                    user_id=str(user_id),
                    submission_id=f"{final_id}:{index}",
                    requested_session_id=str(document["session_id"]),
                    session_data=session_data,
                    assessment_type=assessment_type,
                    questions=[question],
                    grading=grading,
                    observed_at=now,
                    source_kind="final_assessment",
                )
            except Exception:
                # A mastery update failure must not lose the learner's result.
                pass

        total = len(questions)
        percent = round(score / total * 100)
        mastery = self._current_mastery(user_id, list(concept_stats))
        concepts = [
            {
                "concept_id": concept_id,
                "concept_label": concept_names.get(concept_id) or concept_id,
                "asked": stats["asked"],
                "missed": stats["missed"],
                "current_mastery": round(mastery[concept_id], 4) if concept_id in mastery else None,
                "band": mastery_band(mastery[concept_id]).value if concept_id in mastery else None,
            }
            for concept_id, stats in concept_stats.items()
            if concept_id in concept_names
        ]
        concepts.sort(key=lambda item: (-item["missed"], item["current_mastery"] or 0))
        passed = percent >= FINAL_PASS_PERCENT
        result = {
            "score": score,
            "total": total,
            "percent": percent,
            "passed": passed,
            "pass_percent": FINAL_PASS_PERCENT,
            "questions": review,
            "concepts": concepts,
            "retry_available_at": None if passed else _iso(now + FINAL_RETRY_COOLDOWN),
        }
        completed = self._db.final_assessments.find_one_and_update(
            {"_id": final_id, "status": "grading"},
            {
                "$set": {
                    "status": "completed",
                    "score": score,
                    "total": total,
                    "percent": percent,
                    "passed": passed,
                    "result": result,
                    "completed_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return self._public(completed)
