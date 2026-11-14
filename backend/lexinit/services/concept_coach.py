"""In-course coaching: small, targeted responses to a learner's mistakes.

Instead of answering every wrong answer with a whole new course, the coach
works at the size of the gap, inside the course the learner is already in:

* fix-it card    - why the chosen answer was tempting but wrong, the key idea,
                   and one fresh check question on the same idea
* explanation    - one concept re-explained in a different style
* practice set   - three fresh questions on one concept
* question refill - new module assessment questions, so a reattempt tests
                   understanding rather than memory of revealed answers

Check questions keep their answers on the server until answered, and every
answer becomes mastery evidence.
"""

from __future__ import annotations

import datetime
import hashlib
import json
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from backend.lexinit.api.errors import ApiError
from backend.lexinit.domain.assessment.grading import ASSESSMENT_FIELDS
from backend.lexinit.domain.mastery import calculate_mastery, choose_adaptation
from backend.lexinit.domain.mastery.calculator import mastery_band, retention
from backend.lexinit.repositories.adaptive import AdaptiveLearningRepository
from backend.lexinit.schemas.adaptive import MasteryEvidence
from backend.lexinit.schemas.assessment import AssessmentType
from backend.lexinit.schemas.generated_content import MCQDraft, OneWordDraft, TrueFalseDraft
from backend.lexinit.schemas.generation import Difficulty
from backend.lexinit.services.curriculum import StructuredGenerator
from backend.lexinit.services.learner_context import learner_context_instruction
from backend.lexinit.services.question_quality import verify_answer_keys


COACH_PROMPT_VERSION = "coach-v1"
EXPLANATION_STYLES = {
    "simpler": "Explain it in the simplest possible words, as if to someone meeting the idea for the first time. Short sentences, no jargon without defining it.",
    "analogy": "Explain it through one strong everyday analogy, then map each part of the analogy back to the real concept and say where the analogy stops working.",
    "example": "Explain it by walking through one concrete worked example with real values, step by step, then state the general rule the example shows.",
    "step_by_step": "Explain it as a numbered sequence of small steps, each building on the previous one, ending with a one-line summary.",
}
FIX_IT_EVIDENCE_WEIGHT = 0.6
PRACTICE_EVIDENCE_WEIGHT = 0.8
PRACTICE_SET_SIZE = 3
MAX_MODULE_BANK_PER_TYPE = 18
DAILY_MIX_SIZE = 5
PRE_CHECK_SIZE = 4
PRE_CHECK_EVIDENCE_WEIGHT = 0.8
DAILY_MIX_EVIDENCE_WEIGHT = 0.9
MAX_REFILL = 4


class FixItDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    why_tempting: str = Field(min_length=10, max_length=600)
    key_idea: str = Field(min_length=10, max_length=600)
    check_question: MCQDraft


class ExplanationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explanation: str = Field(min_length=40, max_length=3000)
    takeaway: str = Field(min_length=5, max_length=300)


class PracticeSetDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    questions: list[MCQDraft] = Field(min_length=PRACTICE_SET_SIZE, max_length=PRACTICE_SET_SIZE)


class MCQRefill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[MCQDraft] = Field(min_length=1, max_length=MAX_REFILL)


class TrueFalseRefill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[TrueFalseDraft] = Field(min_length=1, max_length=MAX_REFILL)


class OneWordRefill(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[OneWordDraft] = Field(min_length=1, max_length=MAX_REFILL)


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _hash(*parts: object) -> str:
    content = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ConceptCoachService:
    def __init__(
        self,
        *,
        db,
        generator: StructuredGenerator,
        adaptive_repository: AdaptiveLearningRepository,
    ) -> None:
        self._db = db
        self._generator = generator
        self._adaptive = adaptive_repository

    # ------------------------------------------------------------------ fix-it

    def fix_it(self, *, user_id: str, submission_id: str, question_index: int) -> dict[str, Any]:
        user_object_id = ObjectId(user_id)
        submission = self._owned_submission(user_object_id, submission_id)
        questions = submission.get("questions") or []
        feedback = submission.get("feedback") or []
        if not 0 <= question_index < len(questions) or question_index >= len(feedback):
            raise ApiError("Unknown question.", status_code=404, code="question_not_found")
        if feedback[question_index].get("correct"):
            raise ApiError(
                "This question was answered correctly.",
                status_code=409,
                code="question_already_correct",
            )

        fix_id = f"fix_{_hash(submission_id, question_index)[:32]}"
        existing = self._db.coach_items.find_one({"_id": fix_id, "user_id": user_object_id})
        if existing:
            return self._public_fix_it(existing)

        session_data = self._session(user_object_id, submission.get("session_id"))
        snapshot = questions[question_index]
        item_feedback = feedback[question_index]
        ref = submission_question_refs(self._db, submission)[question_index]
        concept_ids = ref["concept_ids"]
        context = _concept_context(session_data, concept_ids, ref.get("module_id"))

        prompt = (
            "A learner answered an assessment question incorrectly. Write a short, kind, "
            "specific correction.\n"
            "- why_tempting: explain why the learner's answer looks plausible and exactly what "
            "is wrong with it. Address the learner as 'you'. Name the confusion, do not just "
            "restate the right answer.\n"
            "- key_idea: the one idea that, once understood, makes the right answer obvious.\n"
            "- check_question: ONE new multiple-choice question that tests the same idea in a "
            "different way (a new scenario or phrasing, never a reworded copy of the original). "
            "Four unique options, one correct. Add misconceptions for tempting wrong options.\n"
            "Stay strictly within the course material below.\n\n"
            f"ORIGINAL QUESTION: {snapshot.get('question')}\n"
            f"OPTIONS: {json.dumps(snapshot.get('options') or [], ensure_ascii=False)}\n"
            f"LEARNER'S ANSWER: {_readable_answer(snapshot)}\n"
            f"CORRECT ANSWER: {_readable_correct(snapshot, item_feedback)}\n"
            f"STORED EXPLANATION: {item_feedback.get('explanation') or ''}\n"
            f"KNOWN MISCONCEPTION FOR THIS ANSWER: {ref.get('misconception') or 'not recorded'}\n\n"
            f"COURSE MATERIAL:\n{context['text']}\n\n{context['learner']}"
        )
        draft = self._generate(prompt, FixItDraft, temperature=0.3)

        check = self._store_check(
            user_object_id=user_object_id,
            session_data=session_data,
            draft=draft.check_question,
            concept_ids=concept_ids,
            module_id=ref.get("module_id"),
            difficulty=ref.get("difficulty") or context["difficulty"],
            source="fix_it",
            evidence_weight=FIX_IT_EVIDENCE_WEIGHT,
            seed=fix_id,
        )
        document = {
            "_id": fix_id,
            "user_id": user_object_id,
            "kind": "fix_it",
            "session_id": session_data["_id"],
            "submission_id": str(submission["_id"]),
            "question_index": question_index,
            "concept_ids": concept_ids,
            "why_tempting": draft.why_tempting.strip(),
            "key_idea": draft.key_idea.strip(),
            "check_id": check["_id"],
            "prompt_version": COACH_PROMPT_VERSION,
            "created_at": utcnow(),
        }
        try:
            self._db.coach_items.insert_one(document)
        except DuplicateKeyError:
            document = self._db.coach_items.find_one({"_id": fix_id, "user_id": user_object_id})
        return self._public_fix_it(document)

    def _public_fix_it(self, document: dict[str, Any]) -> dict[str, Any]:
        check = self._db.coach_checks.find_one(
            {"_id": document["check_id"], "user_id": document["user_id"]}
        )
        return {
            "fix_id": document["_id"],
            "question_index": document["question_index"],
            "why_tempting": document["why_tempting"],
            "key_idea": document["key_idea"],
            "check": _public_check(check) if check else None,
        }

    # ------------------------------------------------------------- explanation

    def explain(self, *, user_id: str, session_id: str, concept_id: str, style: str) -> dict[str, Any]:
        if style not in EXPLANATION_STYLES:
            raise ApiError("Unknown explanation style.", code="invalid_explanation_style")
        user_object_id = ObjectId(user_id)
        session_data = self._session(user_object_id, session_id)
        label = _concept_label(session_data, concept_id)
        if label is None:
            raise ApiError("Unknown concept.", status_code=404, code="concept_not_found")

        item_id = f"explain_{_hash(user_id, session_data['_id'], concept_id, style)[:32]}"
        existing = self._db.coach_items.find_one({"_id": item_id, "user_id": user_object_id})
        if not existing:
            context = _concept_context(session_data, [concept_id], None)
            misconceptions = self._learner_misconceptions(user_object_id, concept_id)
            prompt = (
                f"Re-explain one concept for a learner who did not fully get it the first time.\n"
                f"CONCEPT: {label}\n"
                f"STYLE: {EXPLANATION_STYLES[style]}\n"
                "Write 120-220 words of plain Markdown (short paragraphs or a short list; no "
                "headings, no tables). Do not repeat the course text; give a genuinely different "
                "way in. Then give a one-sentence takeaway.\n"
                + (
                    "The learner has shown these confusions, so address them directly: "
                    + "; ".join(misconceptions)
                    + "\n"
                    if misconceptions
                    else ""
                )
                + f"Stay strictly within the course material below.\n\nCOURSE MATERIAL:\n{context['text']}\n\n{context['learner']}"
            )
            draft = self._generate(prompt, ExplanationDraft, temperature=0.5)
            existing = {
                "_id": item_id,
                "user_id": user_object_id,
                "kind": "explanation",
                "session_id": session_data["_id"],
                "concept_id": concept_id,
                "concept_label": label,
                "style": style,
                "explanation": draft.explanation.strip(),
                "takeaway": draft.takeaway.strip(),
                "prompt_version": COACH_PROMPT_VERSION,
                "created_at": utcnow(),
            }
            try:
                self._db.coach_items.insert_one(existing)
            except DuplicateKeyError:
                existing = self._db.coach_items.find_one({"_id": item_id, "user_id": user_object_id})
        return {
            "explanation_id": existing["_id"],
            "concept_id": concept_id,
            "concept_label": existing["concept_label"],
            "style": existing["style"],
            "explanation": existing["explanation"],
            "takeaway": existing["takeaway"],
            "helpful": existing.get("helpful"),
        }

    def explanation_feedback(self, *, user_id: str, explanation_id: str, helpful: bool) -> dict[str, Any]:
        user_object_id = ObjectId(user_id)
        item = self._db.coach_items.find_one_and_update(
            {"_id": explanation_id, "user_id": user_object_id, "kind": "explanation"},
            {"$set": {"helpful": bool(helpful), "feedback_at": utcnow()}},
            return_document=ReturnDocument.AFTER,
        )
        if not item:
            raise ApiError("Explanation not found.", status_code=404, code="explanation_not_found")
        if helpful:
            # Remember the style that worked so it is offered first next time.
            self._db.users.update_one(
                {"_id": user_object_id},
                {"$set": {"coach_preferences.explanation_style": item["style"]}},
            )
        return {"explanation_id": explanation_id, "helpful": bool(helpful)}

    def preferences(self, *, user_id: str) -> dict[str, Any]:
        user = self._db.users.find_one({"_id": ObjectId(user_id)}, {"coach_preferences": 1}) or {}
        style = (user.get("coach_preferences") or {}).get("explanation_style")
        return {"explanation_style": style if style in EXPLANATION_STYLES else None}

    # ---------------------------------------------------------------- practice

    def practice(self, *, user_id: str, session_id: str, concept_id: str) -> dict[str, Any]:
        user_object_id = ObjectId(user_id)
        session_data = self._session(user_object_id, session_id)
        label = _concept_label(session_data, concept_id)
        if label is None:
            raise ApiError("Unknown concept.", status_code=404, code="concept_not_found")
        context = _concept_context(session_data, [concept_id], None)
        avoid = _existing_question_stems(session_data, concept_id) + [
            item["question"]
            for item in self._db.coach_checks.find(
                {"user_id": user_object_id, "session_id": session_data["_id"], "concept_ids": concept_id},
                {"question": 1},
            )
            .sort("created_at", -1)
            .limit(12)
        ]
        misconceptions = self._learner_misconceptions(user_object_id, concept_id)
        prompt = (
            f"Write exactly {PRACTICE_SET_SIZE} new multiple-choice practice questions on one concept.\n"
            f"CONCEPT: {label}\n"
            "Order them easy, then medium, then hard. The easy one checks the definition, the "
            "medium one applies it, the hard one needs reasoning about a new situation. Four "
            "unique options each, one correct, with a clear explanation and misconceptions for "
            "tempting wrong options.\n"
            + (
                "The learner has shown these confusions; make at least one question target them: "
                + "; ".join(misconceptions)
                + "\n"
                if misconceptions
                else ""
            )
            + "Do not repeat or lightly reword any of these existing questions:\n"
            + "\n".join(f"- {stem}" for stem in avoid[:20])
            + f"\n\nStay strictly within the course material below.\n\nCOURSE MATERIAL:\n{context['text']}\n\n{context['learner']}"
        )
        draft = self._generate(prompt, PracticeSetDraft, temperature=0.5)
        set_id = f"practice_{_hash(user_id, session_data['_id'], concept_id, utcnow().isoformat())[:24]}"
        difficulties = [Difficulty.EASY.value, Difficulty.MEDIUM.value, Difficulty.HARD.value]
        checks = [
            self._store_check(
                user_object_id=user_object_id,
                session_data=session_data,
                draft=question,
                concept_ids=[concept_id],
                module_id=context["module_id"],
                difficulty=difficulties[index % len(difficulties)],
                source="practice",
                evidence_weight=PRACTICE_EVIDENCE_WEIGHT,
                seed=f"{set_id}:{index}",
                set_id=set_id,
            )
            for index, question in enumerate(draft.questions)
        ]
        return {
            "set_id": set_id,
            "concept_id": concept_id,
            "concept_label": label,
            "checks": [_public_check(check) for check in checks],
        }

    # --------------------------------------------------------------- pre-check

    def module_overview(self, *, user_id: str, session_id: str, module_id: str) -> dict[str, Any]:
        """A module's concepts with the learner's current mastery, plus the
        pre-check if one was already created."""
        user_object_id = ObjectId(user_id)
        session_data = self._session(user_object_id, session_id)
        module = _module(session_data, module_id)
        if not module:
            raise ApiError("Unknown course module.", status_code=404, code="module_not_found")
        now = utcnow()
        names = {
            item["concept_id"]: str(item.get("name") or "")
            for item in module.get("concepts") or []
            if item.get("concept_id")
        }
        mastery = {
            record["concept_id"]: record
            for record in self._db.concept_mastery.find(
                {"user_id": user_object_id, "concept_id": {"$in": list(names)}}
            )
        }
        concepts = []
        for concept_id, label in names.items():
            record = mastery.get(concept_id)
            current = None
            if record:
                current = round(
                    float(record.get("mastery_probability") or 0)
                    * retention(record["last_practiced_at"], record["next_review_at"], now),
                    4,
                )
            concepts.append(
                {
                    "concept_id": concept_id,
                    "concept_label": label,
                    "asked": 0,
                    "missed": 0,
                    "current_mastery": current,
                    "band": mastery_band(current).value if current is not None else None,
                }
            )
        checks = list(
            self._db.coach_checks.find(
                {"user_id": user_object_id, "set_id": _pre_check_set_id(user_id, session_data["_id"], module_id)}
            ).sort("order", 1)
        )
        return {
            "module_id": module_id,
            "module_title": str(module.get("title") or ""),
            "concepts": concepts,
            # Offer a pre-check only before the learner has evidence here.
            "pre_check_available": not checks and not mastery,
            "pre_check": self._public_pre_check(checks) if checks else None,
        }

    def pre_check(self, *, user_id: str, session_id: str, module_id: str) -> dict[str, Any]:
        """One diagnostic question per concept, taken before studying a
        module, so learners can skip what they already know."""
        user_object_id = ObjectId(user_id)
        session_data = self._session(user_object_id, session_id)
        module = _module(session_data, module_id)
        if not module:
            raise ApiError("Unknown course module.", status_code=404, code="module_not_found")
        set_id = _pre_check_set_id(user_id, session_data["_id"], module_id)
        existing = list(
            self._db.coach_checks.find({"user_id": user_object_id, "set_id": set_id}).sort("order", 1)
        )
        if existing:
            return self._public_pre_check(existing)

        concepts = [item for item in module.get("concepts") or [] if item.get("concept_id")][:PRE_CHECK_SIZE]
        context = _concept_context(session_data, [item["concept_id"] for item in concepts], module_id)
        prompt = (
            f"Write a diagnostic pre-check: exactly {len(concepts)} multiple-choice questions, one per "
            "concept below, in the same order. Each question must separate someone who already "
            "understands the concept from someone who does not: test the core idea, not trivia, and "
            "make the wrong options the mistakes a beginner would actually make. Four unique options, "
            "one correct, a concise explanation, and misconceptions for tempting wrong options.\n"
            "CONCEPTS: "
            + "; ".join(str(item.get("name")) for item in concepts)
            + f"\n\nCOURSE MATERIAL:\n{context['text']}"
        )

        class PreCheckDraft(BaseModel):
            model_config = ConfigDict(extra="forbid")
            questions: list[MCQDraft] = Field(min_length=len(concepts), max_length=len(concepts))

        draft = self._generate(prompt, PreCheckDraft, temperature=0.4)
        checks = [
            self._store_check(
                user_object_id=user_object_id,
                session_data=session_data,
                draft=question,
                concept_ids=[concept["concept_id"]],
                module_id=module_id,
                difficulty=context["difficulty"],
                source="pre_check",
                evidence_weight=PRE_CHECK_EVIDENCE_WEIGHT,
                seed=f"{set_id}:{index}",
                set_id=set_id,
                extra={"order": index, "concept_label": str(concept.get("name") or "")},
            )
            for index, (concept, question) in enumerate(zip(concepts, draft.questions))
        ]
        return self._public_pre_check(checks)

    @staticmethod
    def _public_pre_check(checks: list[dict[str, Any]]) -> dict[str, Any]:
        answered = [item for item in checks if item.get("answered_at") is not None]
        return {
            "total": len(checks),
            "answered": len(answered),
            "correct": sum(1 for item in answered if item.get("correct")),
            "checks": [
                {**_public_check(item), "concept_label": item.get("concept_label") or ""}
                for item in checks
            ],
        }

    # --------------------------------------------------------------- daily mix

    def daily_mix_status(self, *, user_id: str) -> dict[str, Any]:
        """Today's mix if it exists, otherwise how many concepts are waiting."""
        user_object_id = ObjectId(user_id)
        set_id = _daily_set_id(user_id)
        checks = list(
            self._db.coach_checks.find({"user_id": user_object_id, "set_id": set_id}).sort("order", 1)
        )
        if checks:
            return self._public_daily_mix(set_id, checks)
        targets = self._daily_targets(user_object_id)
        return {
            "set_id": None,
            "ready": False,
            "waiting_concepts": len(targets),
            "due_concepts": sum(1 for item in targets if item["due"]),
            "checks": [],
        }

    def daily_mix(self, *, user_id: str) -> dict[str, Any]:
        """Create (once per day) a short interleaved review: concepts due for
        review first, then the weakest ones, drawn from every course."""
        user_object_id = ObjectId(user_id)
        set_id = _daily_set_id(user_id)
        existing = list(
            self._db.coach_checks.find({"user_id": user_object_id, "set_id": set_id}).sort("order", 1)
        )
        if existing:
            return self._public_daily_mix(set_id, existing)

        targets = self._daily_targets(user_object_id)
        if not targets:
            return {"set_id": None, "ready": False, "waiting_concepts": 0, "due_concepts": 0, "checks": []}

        items = []
        for index, target in enumerate(targets):
            context = _concept_context(target["session"], [target["concept_id"]], None)
            items.append(
                {
                    "position": index + 1,
                    "course": target["session"].get("topic"),
                    "concept": target["label"],
                    "level": target["difficulty"],
                    "learner_confusions": self._learner_misconceptions(user_object_id, target["concept_id"]),
                    "material": json.loads(context["text"]).get("knowledge"),
                }
            )
        prompt = (
            f"Write a short mixed review: exactly {len(items)} multiple-choice questions, one per item "
            "below, in the same order. Each question tests that item's concept at the given level "
            "(easy = recall the idea, medium = apply it, hard = reason about a new situation). Four "
            "unique options, one correct, a concise explanation, and misconceptions for tempting wrong "
            "options. Where learner_confusions are listed, target them. Use only each item's material.\n\n"
            + json.dumps(items, ensure_ascii=False)[:20000]
        )

        class DailyMixDraft(BaseModel):
            model_config = ConfigDict(extra="forbid")
            questions: list[MCQDraft] = Field(min_length=len(items), max_length=len(items))

        draft = self._generate(prompt, DailyMixDraft, temperature=0.5)
        checks = []
        for index, (target, question) in enumerate(zip(targets, draft.questions)):
            check = self._store_check(
                user_object_id=user_object_id,
                session_data=target["session"],
                draft=question,
                concept_ids=[target["concept_id"]],
                module_id=target["module_id"],
                difficulty=target["difficulty"],
                source="daily_mix",
                evidence_weight=DAILY_MIX_EVIDENCE_WEIGHT,
                seed=f"{set_id}:{index}",
                set_id=set_id,
                extra={
                    "order": index,
                    "concept_label": target["label"],
                    "course_topic": str(target["session"].get("topic") or ""),
                    "reason": "due" if target["due"] else "weak",
                },
            )
            checks.append(check)
        return self._public_daily_mix(set_id, checks)

    def _daily_targets(self, user_object_id: ObjectId) -> list[dict[str, Any]]:
        now = utcnow()
        candidates = []
        for record in self._db.concept_mastery.find({"user_id": user_object_id}):
            remembered = retention(record["last_practiced_at"], record["next_review_at"], now)
            current = float(record.get("mastery_probability") or 0) * remembered
            next_review = record["next_review_at"]
            if next_review.tzinfo is None:
                next_review = next_review.replace(tzinfo=datetime.timezone.utc)
            due = next_review <= now
            if not due and current >= 0.65:
                continue
            candidates.append((0 if due else 1, current, record, due))
        candidates.sort(key=lambda item: (item[0], item[1]))

        targets: list[dict[str, Any]] = []
        sessions: dict[Any, dict[str, Any] | None] = {}
        for _, current, record, due in candidates:
            if len(targets) >= DAILY_MIX_SIZE:
                break
            concept_id = record["concept_id"]
            evidence = self._db.mastery_evidence.find_one(
                {"user_id": user_object_id, "concept_id": concept_id}, sort=[("observed_at", -1)]
            )
            session_key = (evidence or {}).get("session_id")
            if session_key is None:
                continue
            if session_key not in sessions:
                try:
                    sessions[session_key] = self._session(user_object_id, session_key)
                except ApiError:
                    sessions[session_key] = None
            session_data = sessions[session_key]
            if not session_data:
                continue
            label = _concept_label(session_data, concept_id)
            if not label:
                continue
            module = next(
                (
                    item
                    for item in _modules(session_data)
                    if any(concept.get("concept_id") == concept_id for concept in item.get("concepts") or [])
                ),
                None,
            )
            targets.append(
                {
                    "concept_id": concept_id,
                    "label": label,
                    "session": session_data,
                    "module_id": module.get("module_id") if module else None,
                    "due": due,
                    "difficulty": "easy" if current < 0.4 else "medium" if current < 0.65 else "hard",
                }
            )
        return targets

    @staticmethod
    def _public_daily_mix(set_id: str, checks: list[dict[str, Any]]) -> dict[str, Any]:
        answered = [item for item in checks if item.get("answered_at") is not None]
        return {
            "set_id": set_id,
            "ready": True,
            "total": len(checks),
            "answered": len(answered),
            "correct": sum(1 for item in answered if item.get("correct")),
            "checks": [
                {
                    **_public_check(item),
                    "session_id": str(item["session_id"]),
                    "concept_label": item.get("concept_label") or "",
                    "course_topic": item.get("course_topic") or "",
                    "reason": item.get("reason") or "weak",
                }
                for item in checks
            ],
        }

    # ------------------------------------------------------------ check answer

    def answer_check(self, *, user_id: str, check_id: str, answer: int) -> dict[str, Any]:
        user_object_id = ObjectId(user_id)
        check = self._db.coach_checks.find_one({"_id": check_id, "user_id": user_object_id})
        if not check:
            raise ApiError("Question not found.", status_code=404, code="check_not_found")
        if not isinstance(answer, int) or isinstance(answer, bool) or not 0 <= answer < len(check["options"]):
            raise ApiError("Choose one of the options.", code="invalid_check_answer")

        now = utcnow()
        claimed = self._db.coach_checks.find_one_and_update(
            {"_id": check_id, "user_id": user_object_id, "answered_at": None},
            {
                "$set": {
                    "answered_at": now,
                    "selected_answer": answer,
                    "correct": answer == check["answer"],
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not claimed:
            # Already answered: return the stored outcome, never a second grade.
            return self._check_result(self._db.coach_checks.find_one({"_id": check_id}), [])

        correct = bool(claimed["correct"])
        misconception_label = None
        if not correct:
            misconception_label = (claimed.get("misconception_map") or {}).get(chr(ord("A") + answer))
        mastery_updates = []
        labels = _concept_labels(self._session(user_object_id, claimed["session_id"]))
        for concept_id in claimed.get("concept_ids") or []:
            evidence = MasteryEvidence(
                evidence_id=f"evidence_{_hash(check_id, concept_id)[:32]}",
                user_id=user_id,
                submission_id=check_id,
                session_id=str(claimed["session_id"]),
                question_id=check_id,
                concept_id=concept_id,
                concept_label=labels.get(concept_id) or claimed.get("concept_label") or concept_id,
                correct=correct,
                difficulty=Difficulty(claimed.get("difficulty") or "medium"),
                misconception_id=(
                    f"misconception_{_hash(misconception_label.casefold())[:24]}"
                    if misconception_label
                    else None
                ),
                misconception_label=misconception_label,
                observed_at=now,
                source_kind="practice",
                evidence_weight=float(claimed.get("evidence_weight") or PRACTICE_EVIDENCE_WEIGHT),
                guess_probability=round(1 / len(claimed["options"]), 4),
            )
            self._adaptive.add_evidence(evidence)
            mastery = calculate_mastery(self._adaptive.list_evidence(user_id, concept_id))
            self._adaptive.save_mastery(mastery)
            self._adaptive.save_decision(
                choose_adaptation(
                    mastery,
                    evidence,
                    decision_id=f"decision_{_hash(check_id, concept_id)[:32]}",
                )
            )
            mastery_updates.append(mastery.public_dict(now))
        return self._check_result(claimed, mastery_updates)

    @staticmethod
    def _check_result(check: dict[str, Any], mastery_updates: list[dict[str, Any]]) -> dict[str, Any]:
        selected = check.get("selected_answer")
        misconception = None
        if not check.get("correct") and isinstance(selected, int):
            misconception = (check.get("misconception_map") or {}).get(chr(ord("A") + selected))
        return {
            "check_id": check["_id"],
            "correct": bool(check.get("correct")),
            "selected_answer": selected,
            "correct_answer": check["answer"],
            "explanation": check.get("explanation") or "",
            "misconception": misconception,
            "mastery_updates": mastery_updates,
        }

    # --------------------------------------------------------- question refill

    def refill_module_questions(
        self,
        *,
        user_id: ObjectId,
        session_data: dict[str, Any],
        module_id: str,
        assessment_type: AssessmentType,
        count: int,
    ) -> dict[str, Any]:
        """Append fresh questions for one module and type to the course and
        return the updated course document."""
        count = max(1, min(MAX_REFILL, int(count)))
        module = _module(session_data, module_id)
        if not module:
            return session_data
        field = next(
            (name for name in ASSESSMENT_FIELDS[assessment_type] if isinstance(session_data.get(name), list)),
            ASSESSMENT_FIELDS[assessment_type][0],
        )
        existing = [
            item
            for item in session_data.get(field) or []
            if isinstance(item, dict) and item.get("module_id") == module_id
        ]
        if len(existing) + count > MAX_MODULE_BANK_PER_TYPE:
            return session_data

        concept_ids = [item["concept_id"] for item in module.get("concepts") or [] if item.get("concept_id")]
        context = _concept_context(session_data, concept_ids, module_id)
        schema, shape = {
            AssessmentType.MCQ: (
                MCQRefill,
                "multiple-choice questions with four unique plausible options, one correct_option_index, "
                "and misconceptions for tempting wrong options",
            ),
            AssessmentType.TRUE_FALSE: (
                TrueFalseRefill,
                "unambiguous true/false statements, with misconception_if_wrong where useful",
            ),
            AssessmentType.ONE_WORD: (
                OneWordRefill,
                "questions whose answer is exactly one word or one hyphenated word, with "
                "misconception_if_wrong where useful",
            ),
        }[assessment_type]
        prompt = (
            f"Write exactly {count} new {shape} for one course module. Each needs a concise explanation.\n"
            "Use only concept_ids and objective_ids listed in the course material. The learner has "
            "already seen the answers to the existing questions below, so test the same concepts "
            "through different facts, scenarios or angles. Never reword an existing question.\n"
            + self._weak_spot_instruction(user_id, module)
            + "EXISTING QUESTIONS:\n"
            + "\n".join(f"- {item.get('question')}" for item in existing[:MAX_MODULE_BANK_PER_TYPE])
            + f"\n\nCOURSE MATERIAL:\n{context['text']}"
        )
        draft = self._generate(prompt, schema, temperature=0.4)

        valid_concepts = set(concept_ids)
        valid_objectives = {
            item["objective_id"] for item in module.get("learning_objectives") or [] if item.get("objective_id")
        }
        known_stems = {str(item.get("question") or "").strip().casefold() for item in existing}
        new_questions = []
        for index, item in enumerate(draft.questions[:count]):
            stem = item.question.strip()
            if stem.casefold() in known_stems:
                continue
            known_stems.add(stem.casefold())
            question: dict[str, Any] = {
                "question_id": f"{assessment_type.value}_{_hash(session_data['_id'], module_id, stem)[:20]}",
                "question": stem,
                "explanation": item.explanation.strip(),
                "curriculum_id": session_data.get("curriculum_id"),
                "module_id": module_id,
                "concept_ids": [value for value in item.concept_ids if value in valid_concepts] or concept_ids,
                "objective_ids": [value for value in item.objective_ids if value in valid_objectives]
                or sorted(valid_objectives),
                "difficulty": context["difficulty"],
                "generation_kind": "refill",
                "prompt_version": COACH_PROMPT_VERSION,
                "validation_status": "validated",
            }
            if assessment_type is AssessmentType.MCQ:
                question["options"] = [option.strip() for option in item.options]
                question["answer"] = item.correct_option_index
                question["misconception_map"] = {
                    chr(ord("A") + entry.option_index): entry.misconception.strip()
                    for entry in item.misconceptions
                }
            elif assessment_type is AssessmentType.TRUE_FALSE:
                question["answer"] = item.answer
                question["misconception_map"] = (
                    {str(not item.answer).lower(): item.misconception_if_wrong.strip()}
                    if item.misconception_if_wrong
                    else {}
                )
            else:
                question["answer"] = item.answer.strip()
                question["misconception_map"] = (
                    {"*": item.misconception_if_wrong.strip()} if item.misconception_if_wrong else {}
                )
            new_questions.append(question)

        new_questions = verify_answer_keys(self._generator, new_questions)
        if not new_questions:
            return session_data
        updated = self._db.sessions.find_one_and_update(
            {"_id": session_data["_id"], "user_id": user_id},
            {"$push": {field: {"$each": new_questions}}},
            return_document=ReturnDocument.AFTER,
        )
        return updated or session_data

    def _weak_spot_instruction(self, user_id: ObjectId, module: dict[str, Any]) -> str:
        """Tell the question writer which of the module's concepts this
        learner is weakest on, and which confusions they have shown."""
        names = {
            item["concept_id"]: str(item.get("name") or "")
            for item in module.get("concepts") or []
            if item.get("concept_id")
        }
        weak = [
            names[record["concept_id"]]
            for record in self._db.concept_mastery.find(
                {"user_id": user_id, "concept_id": {"$in": list(names)}, "mastery_probability": {"$lt": 0.65}}
            ).sort("mastery_probability", 1)
        ]
        confusions: list[str] = []
        for concept_id in names:
            for label in self._learner_misconceptions(user_id, concept_id):
                if label not in confusions:
                    confusions.append(label)
        lines = []
        if weak:
            lines.append(
                "This learner is weakest on: " + "; ".join(weak[:4])
                + ". Put most questions on these, but keep the module covered."
            )
        if confusions:
            lines.append("They have shown these confusions, so test them: " + "; ".join(confusions[:3]) + ".")
        return ("\n".join(lines) + "\n") if lines else ""

    # ----------------------------------------------------------------- helpers

    def _generate(self, prompt: str, schema: type[BaseModel], *, temperature: float):
        try:
            return self._generator.generate_structured(prompt, schema, temperature=temperature)
        except Exception as exc:
            raise ApiError(
                "The tutor is unavailable right now. Please try again in a moment.",
                status_code=503,
                code="coach_unavailable",
            ) from exc

    def _store_check(
        self,
        *,
        user_object_id: ObjectId,
        session_data: dict[str, Any],
        draft: MCQDraft,
        concept_ids: list[str],
        module_id: str | None,
        difficulty: str,
        source: str,
        evidence_weight: float,
        seed: str,
        set_id: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document = {
            "_id": f"check_{_hash(seed, draft.question)[:32]}",
            "user_id": user_object_id,
            "session_id": session_data["_id"],
            "module_id": module_id,
            "concept_ids": list(concept_ids),
            "question": draft.question.strip(),
            "options": [option.strip() for option in draft.options],
            "answer": draft.correct_option_index,
            "explanation": draft.explanation.strip(),
            "misconception_map": {
                chr(ord("A") + entry.option_index): entry.misconception.strip()
                for entry in draft.misconceptions
            },
            "difficulty": str(difficulty or "medium"),
            "source": source,
            "set_id": set_id,
            "evidence_weight": evidence_weight,
            "answered_at": None,
            "created_at": utcnow(),
            **(extra or {}),
        }
        try:
            self._db.coach_checks.insert_one(document)
        except DuplicateKeyError:
            document = self._db.coach_checks.find_one({"_id": document["_id"]})
        return document

    def _owned_submission(self, user_object_id: ObjectId, submission_id: str) -> dict[str, Any]:
        try:
            object_id = ObjectId(submission_id)
        except Exception as exc:
            raise ApiError("Invalid assessment result.", code="invalid_assessment_submission_id") from exc
        submission = self._db.assessment_submissions.find_one({"_id": object_id, "user_id": user_object_id})
        if not submission:
            raise ApiError(
                "Assessment result not found.",
                status_code=404,
                code="assessment_submission_not_found",
            )
        return submission

    def _session(self, user_object_id: ObjectId, session_id: Any) -> dict[str, Any]:
        candidates: list[Any] = [session_id]
        if isinstance(session_id, str):
            try:
                candidates.append(ObjectId(session_id))
            except Exception:
                pass
        session_data = self._db.sessions.find_one({"_id": {"$in": candidates}, "user_id": user_object_id})
        if not session_data:
            raise ApiError("Course not found.", status_code=404, code="session_not_found")
        return session_data

    def _learner_misconceptions(self, user_object_id: ObjectId, concept_id: str) -> list[str]:
        labels: list[str] = []
        for item in (
            self._db.mastery_evidence.find(
                {
                    "user_id": user_object_id,
                    "concept_id": concept_id,
                    "misconception_label": {"$nin": [None, ""]},
                },
                {"misconception_label": 1},
            )
            .sort("observed_at", -1)
            .limit(6)
        ):
            label = str(item.get("misconception_label") or "").strip()
            if label and label not in labels:
                labels.append(label)
        return labels[:3]


# ---------------------------------------------------------------------------


def _pre_check_set_id(user_id: str, session_id: Any, module_id: str) -> str:
    return f"precheck_{_hash(user_id, session_id, module_id)[:24]}"


def _daily_set_id(user_id: str) -> str:
    return f"daily_{_hash(user_id, utcnow().date().isoformat())[:24]}"


def submission_question_refs(db, submission: dict[str, Any]) -> list[dict[str, Any]]:
    """Concepts, module, difficulty and misconception for each question of a
    submission. Newer submissions store this; older ones are resolved through
    their attempt and the private question bank."""
    questions = submission.get("questions") or []
    stored = submission.get("question_refs")
    if isinstance(stored, list) and len(stored) == len(questions):
        return [dict(item) for item in stored]

    payloads: list[dict[str, Any]] = [{} for _ in questions]
    attempt_id = submission.get("attempt_id")
    if attempt_id:
        try:
            attempt = db.assessment_attempts.find_one({"_id": ObjectId(attempt_id)}, {"answers": 1})
        except Exception:
            attempt = None
        ids = [item.get("question_id") for item in (attempt or {}).get("answers") or []]
        bank = {
            item["_id"]: item
            for item in db.assessment_question_bank.find({"_id": {"$in": [value for value in ids if value]}})
        }
        for index, question_id in enumerate(ids[: len(questions)]):
            document = bank.get(question_id)
            if document:
                payloads[index] = {**document.get("payload", {}), "module_id": document.get("module_id")}
    return [
        question_ref(payload, snapshot, submission.get("assessment_type"))
        for payload, snapshot in zip(payloads, questions)
    ]


def backfill_submission_refs(db) -> int:
    """Copy module and question details onto older results while their
    attempt records still exist (attempts expire about a day after use)."""
    updated = 0
    for submission in db.assessment_submissions.find(
        {"attempt_id": {"$ne": None}, "question_refs": {"$exists": False}}
    ):
        try:
            attempt = db.assessment_attempts.find_one({"_id": ObjectId(submission["attempt_id"])})
        except Exception:
            attempt = None
        if not attempt:
            db.assessment_submissions.update_one(
                {"_id": submission["_id"]}, {"$set": {"question_refs": []}}
            )
            continue
        refs = submission_question_refs(db, submission)
        bank_ids = [item.get("question_id") for item in attempt.get("answers") or []]
        for index, ref in enumerate(refs):
            ref["bank_question_id"] = bank_ids[index] if index < len(bank_ids) else None
        changes: dict[str, Any] = {"question_refs": refs}
        if not submission.get("module_id") and attempt.get("module_id"):
            changes["module_id"] = attempt["module_id"]
        db.assessment_submissions.update_one({"_id": submission["_id"]}, {"$set": changes})
        updated += 1
    return updated


def question_ref(payload: dict[str, Any], snapshot: dict[str, Any], assessment_type: Any) -> dict[str, Any]:
    concept_ids = [str(item) for item in payload.get("concept_ids") or [] if item][:5]
    mapping = payload.get("misconception_map") if isinstance(payload.get("misconception_map"), dict) else {}
    selected = snapshot.get("selected_answer")
    keys = [str(selected).lower(), "*"]
    if str(assessment_type) in {"mcq", AssessmentType.MCQ.value} and isinstance(selected, int):
        keys.insert(0, chr(ord("A") + selected))
    folded = {str(key).strip().lower(): value for key, value in mapping.items()}
    misconception = next((folded[key.lower()] for key in keys if key.lower() in folded), None)
    return {
        "question_id": payload.get("question_id"),
        "concept_ids": concept_ids,
        "module_id": payload.get("module_id"),
        "difficulty": str(payload.get("difficulty") or "") or None,
        "misconception": str(misconception).strip()[:300] if misconception else None,
    }


def _public_check(check: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "check_id": check["_id"],
        "question": check["question"],
        "options": list(check["options"]),
        "difficulty": check.get("difficulty") or "medium",
        "concept_ids": list(check.get("concept_ids") or []),
        "answered": check.get("answered_at") is not None,
    }
    if payload["answered"]:
        payload["result"] = ConceptCoachService._check_result(check, [])
    return payload


def _modules(session_data: dict[str, Any]) -> list[dict[str, Any]]:
    return list((session_data.get("curriculum") or {}).get("modules") or [])


def _module(session_data: dict[str, Any], module_id: str | None) -> dict[str, Any] | None:
    return next((item for item in _modules(session_data) if item.get("module_id") == module_id), None)


def _concept_labels(session_data: dict[str, Any]) -> dict[str, str]:
    return {
        concept["concept_id"]: str(concept.get("name") or concept["concept_id"])
        for module in _modules(session_data)
        for concept in module.get("concepts") or []
        if concept.get("concept_id")
    }


def _concept_label(session_data: dict[str, Any], concept_id: str) -> str | None:
    return _concept_labels(session_data).get(concept_id)


def _existing_question_stems(session_data: dict[str, Any], concept_id: str) -> list[str]:
    stems = []
    for fields in ASSESSMENT_FIELDS.values():
        for field in fields:
            for item in session_data.get(field) or []:
                if isinstance(item, dict) and concept_id in (item.get("concept_ids") or []):
                    stems.append(str(item.get("question") or ""))
    return [stem for stem in stems if stem]


def _concept_context(
    session_data: dict[str, Any], concept_ids: list[str], module_id: str | None
) -> dict[str, Any]:
    """Compact, grounded context for one module: its concepts, objectives and
    knowledge pack."""
    wanted = set(concept_ids)
    module = _module(session_data, module_id) or next(
        (
            item
            for item in _modules(session_data)
            if wanted.intersection(concept.get("concept_id") for concept in item.get("concepts") or [])
        ),
        None,
    )
    payload: dict[str, Any] = {
        "topic": session_data.get("topic"),
        "course_difficulty": session_data.get("difficulty_level"),
    }
    resolved_module_id = None
    if module:
        resolved_module_id = module.get("module_id")
        payload["module"] = {
            "title": module.get("title"),
            "concepts": [
                {
                    "concept_id": concept.get("concept_id"),
                    "name": concept.get("name"),
                    "focus": concept.get("concept_id") in wanted,
                }
                for concept in module.get("concepts") or []
            ],
            "objectives": [
                {
                    "objective_id": objective.get("objective_id"),
                    "description": objective.get("description"),
                }
                for objective in module.get("learning_objectives") or []
            ],
            "common_misconceptions": module.get("common_misconceptions") or [],
        }
        pack = next(
            (
                item
                for item in session_data.get("module_knowledge_packs") or []
                if isinstance(item, dict) and item.get("module_id") == resolved_module_id
            ),
            None,
        )
        if pack:
            payload["knowledge"] = {
                key: pack.get(key)
                for key in ("definitions", "important_facts", "examples", "common_mistakes", "difficulty_boundaries")
                if pack.get(key)
            }
    difficulty = str(session_data.get("difficulty_level") or "medium").lower()
    if difficulty not in {item.value for item in Difficulty}:
        difficulty = Difficulty.MEDIUM.value
    learner = learner_context_instruction(session_data.get("personalization_profile")) or ""
    return {
        "text": json.dumps(payload, ensure_ascii=False)[:9000],
        "learner": learner,
        "module_id": resolved_module_id,
        "difficulty": difficulty,
    }


def _readable_answer(snapshot: dict[str, Any]) -> str:
    if snapshot.get("selected_option"):
        return str(snapshot["selected_option"])
    return str(snapshot.get("selected_answer"))


def _readable_correct(snapshot: dict[str, Any], feedback: dict[str, Any]) -> str:
    correct = feedback.get("correct_answer")
    options = snapshot.get("options") or []
    if isinstance(correct, int) and not isinstance(correct, bool) and 0 <= correct < len(options):
        return str(options[correct])
    return str(correct)
