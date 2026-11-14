"""Boosters: a short remedial unit inside a course.

A booster is the step between quick coaching and a whole new course. When a
concept is still weak after the learner has practised it, the booster
re-teaches up to three such concepts in one focused lesson that starts
simpler and addresses the confusions the learner has actually shown, then
re-checks them with five new questions.

It lives inside the original course, does not use the daily generation
quota (it has its own small allowance), and its answers update mastery, so
the course can show whether the gap closed.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from backend.lexinit.api.errors import ApiError
from backend.lexinit.domain.mastery.calculator import mastery_band, retention
from backend.lexinit.schemas.generated_content import MCQDraft
from backend.lexinit.services.concept_coach import (
    ConceptCoachService,
    _concept_context,
    _concept_labels,
    _hash,
    _modules,
    _public_check,
    utcnow,
)
from backend.lexinit.services.curriculum import StructuredGenerator
from backend.lexinit.services.question_quality import verify_answer_keys


BOOSTER_PROMPT_VERSION = "booster-v1"
BOOSTER_MAX_CONCEPTS = 3
BOOSTER_QUESTIONS = 5
BOOSTER_MIN_QUESTIONS = 3
# A concept qualifies when it is still weak after real practice.
BOOSTER_WEAK_BELOW = 0.5
BOOSTER_MIN_ANSWERS = 3
BOOSTER_PASS_PERCENT = 60
BOOSTER_EVIDENCE_WEIGHT = 0.9
BOOSTER_DAILY_LIMITS = {"free": 2, "plus": 5, "pro": 10}
BOOSTER_DIFFICULTIES = ("easy", "easy", "medium", "medium", "hard")


class BoosterDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=120)
    lesson: str = Field(min_length=300, max_length=9000)
    key_points: list[str] = Field(min_length=3, max_length=5)
    questions: list[MCQDraft] = Field(min_length=BOOSTER_QUESTIONS, max_length=BOOSTER_QUESTIONS)


class BoosterService:
    def __init__(
        self,
        *,
        coach: ConceptCoachService,
        generator: StructuredGenerator,
        verifier: StructuredGenerator | None = None,
    ) -> None:
        self._coach = coach
        self._db = coach._db
        self._generator = generator
        self._verifier = verifier or generator

    # ------------------------------------------------------------------ status

    def status(self, *, user_id: str, session_id: str) -> dict[str, Any]:
        user_object_id = ObjectId(user_id)
        session_data = self._coach._session(user_object_id, session_id)
        targets = self._targets(user_object_id, session_data)
        latest = self._db.coach_items.find_one(
            {"user_id": user_object_id, "session_id": session_data["_id"], "kind": "booster"},
            sort=[("created_at", -1)],
        )
        limit, used = self._allowance(user_object_id)
        return {
            "eligible": bool(targets),
            "concepts": [
                {
                    "concept_id": item["concept_id"],
                    "concept_label": item["label"],
                    "current_mastery": item["current"],
                }
                for item in targets
            ],
            "booster": self._public(latest, session_data) if latest else None,
            "daily_limit": limit,
            "remaining_today": max(0, limit - used),
        }

    # ------------------------------------------------------------------ create

    def create(self, *, user_id: str, session_id: str) -> dict[str, Any]:
        user_object_id = ObjectId(user_id)
        session_data = self._coach._session(user_object_id, session_id)
        latest = self._db.coach_items.find_one(
            {"user_id": user_object_id, "session_id": session_data["_id"], "kind": "booster"},
            sort=[("created_at", -1)],
        )
        if latest:
            public = self._public(latest, session_data)
            if not public["completed"]:
                return public  # finish the open booster first

        targets = self._targets(user_object_id, session_data)
        if not targets:
            raise ApiError(
                "No concept in this course needs a booster right now.",
                status_code=409,
                code="booster_not_needed",
            )
        limit, used = self._allowance(user_object_id)
        if used >= limit:
            raise ApiError(
                f"You have used today's {limit} boosters. Try again tomorrow.",
                status_code=429,
                code="booster_limit_reached",
            )

        draft = self._write(user_object_id, session_data, targets)
        target_ids = [item["concept_id"] for item in targets]
        labels = {item["concept_id"]: item["label"] for item in targets}
        questions = []
        for index, question in enumerate(draft.questions):
            concept_ids = [value for value in question.concept_ids if value in labels][:2] or [
                target_ids[index % len(target_ids)]
            ]
            questions.append(
                {
                    "draft": question,
                    "concept_ids": concept_ids,
                    "question": question.question.strip(),
                    "options": [option.strip() for option in question.options],
                    "answer": question.correct_option_index,
                }
            )
        verified = verify_answer_keys(self._verifier, questions)
        if len(verified) >= BOOSTER_MIN_QUESTIONS:
            questions = verified

        now = utcnow()
        booster_id = f"booster_{_hash(user_id, session_data['_id'], now.isoformat())[:28]}"
        module_by_concept = {
            concept.get("concept_id"): module.get("module_id")
            for module in _modules(session_data)
            for concept in module.get("concepts") or []
        }
        check_ids = []
        for index, question in enumerate(questions):
            check = self._coach._store_check(
                user_object_id=user_object_id,
                session_data=session_data,
                draft=question["draft"],
                concept_ids=question["concept_ids"],
                module_id=module_by_concept.get(question["concept_ids"][0]),
                difficulty=BOOSTER_DIFFICULTIES[index % len(BOOSTER_DIFFICULTIES)],
                source="booster",
                evidence_weight=BOOSTER_EVIDENCE_WEIGHT,
                seed=f"{booster_id}:{index}",
                set_id=booster_id,
                extra={"order": index, "concept_label": labels[question["concept_ids"][0]]},
            )
            check_ids.append(check["_id"])

        document = {
            "_id": booster_id,
            "user_id": user_object_id,
            "kind": "booster",
            "session_id": session_data["_id"],
            "concept_ids": target_ids,
            "concepts": [
                {
                    "concept_id": item["concept_id"],
                    "concept_label": item["label"],
                    "mastery_before": item["current"],
                }
                for item in targets
            ],
            "title": draft.title.strip(),
            "lesson": draft.lesson.strip(),
            "key_points": [point.strip() for point in draft.key_points if point.strip()],
            "check_ids": check_ids,
            "prompt_version": BOOSTER_PROMPT_VERSION,
            "created_at": now,
        }
        self._db.coach_items.insert_one(document)
        return self._public(document, session_data)

    # ----------------------------------------------------------------- helpers

    def _write(self, user_object_id: ObjectId, session_data: dict[str, Any], targets) -> BoosterDraft:
        contexts = []
        seen_modules = set()
        for item in targets:
            context = _concept_context(session_data, [item["concept_id"]], None)
            if context["module_id"] in seen_modules:
                continue
            seen_modules.add(context["module_id"])
            contexts.append(json.loads(context["text"]))
        learner = _concept_context(session_data, [targets[0]["concept_id"]], None)["learner"]
        payload = [
            {
                "concept_id": item["concept_id"],
                "name": item["label"],
                "learner_mastery_percent": round(item["current"] * 100),
                "confusions_the_learner_has_shown": self._coach._learner_misconceptions(
                    user_object_id, item["concept_id"]
                ),
            }
            for item in targets
        ]
        prompt = (
            "A learner has practised these concepts several times and still gets them wrong. "
            "Write a short booster that fixes that.\n\n"
            f"COURSE MATERIAL (JSON):\n{json.dumps(contexts, ensure_ascii=False)[:16000]}\n\n"
            f"CONCEPTS TO FIX (JSON):\n{json.dumps(payload, ensure_ascii=False)}\n\n"
            "TASK:\n"
            "- title: a short, plain title naming what the booster fixes.\n"
            "- lesson: 350 to 650 words of Markdown. Teach each concept again from the simplest "
            "correct idea, as if the first explanation did not land. For each concept: say what it "
            "is in one or two plain sentences, name the confusion the learner has shown and why it "
            "is wrong, then give one small worked example. Use a short heading per concept. Do not "
            "copy the course text; explain it a different way.\n"
            "- key_points: three to five one-sentence takeaways.\n"
            f"- questions: exactly {BOOSTER_QUESTIONS} new multiple-choice questions that re-check "
            "these concepts, ordered from easiest to hardest, with four unique options, one correct, "
            "a concise explanation, and misconceptions for tempting wrong options. List the "
            "concept_ids each question tests, using only the concept_ids above. Every concept must "
            "be tested at least once.\n"
            "Stay strictly within the course material.\n\n"
            f"{learner}"
        )
        try:
            return self._generator.generate_structured(prompt, BoosterDraft, temperature=0.4)
        except Exception as exc:
            raise ApiError(
                "The booster could not be prepared. Please try again in a moment.",
                status_code=503,
                code="booster_unavailable",
            ) from exc

    def _targets(self, user_object_id: ObjectId, session_data: dict[str, Any]) -> list[dict[str, Any]]:
        labels = _concept_labels(session_data)
        now = utcnow()
        weak = []
        for record in self._db.concept_mastery.find(
            {"user_id": user_object_id, "concept_id": {"$in": list(labels)}}
        ):
            if int(record.get("attempts") or 0) < BOOSTER_MIN_ANSWERS:
                continue
            current = float(record.get("mastery_probability") or 0) * retention(
                record["last_practiced_at"], record["next_review_at"], now
            )
            if current < BOOSTER_WEAK_BELOW:
                weak.append(
                    {
                        "concept_id": record["concept_id"],
                        "label": labels[record["concept_id"]],
                        "current": round(current, 4),
                    }
                )
        weak.sort(key=lambda item: item["current"])
        return weak[:BOOSTER_MAX_CONCEPTS]

    def _allowance(self, user_object_id: ObjectId) -> tuple[int, int]:
        user = self._db.users.find_one({"_id": user_object_id}, {"plan": 1}) or {}
        plan = str(user.get("plan") or "free").strip().lower()
        limit = BOOSTER_DAILY_LIMITS.get(plan, BOOSTER_DAILY_LIMITS["free"])
        since = utcnow() - datetime.timedelta(hours=24)
        used = self._db.coach_items.count_documents(
            {"user_id": user_object_id, "kind": "booster", "created_at": {"$gte": since}}
        )
        return limit, used

    def _public(self, document: dict[str, Any], session_data: dict[str, Any]) -> dict[str, Any]:
        checks = list(
            self._db.coach_checks.find(
                {"user_id": document["user_id"], "set_id": document["_id"]}
            ).sort("order", 1)
        )
        answered = [item for item in checks if item.get("answered_at") is not None]
        correct = sum(1 for item in answered if item.get("correct"))
        completed = bool(checks) and len(answered) == len(checks)
        percent = round(correct / len(checks) * 100) if checks else 0
        now = utcnow()
        mastery = {
            record["concept_id"]: record
            for record in self._db.concept_mastery.find(
                {"user_id": document["user_id"], "concept_id": {"$in": document["concept_ids"]}}
            )
        }
        concepts = []
        for item in document["concepts"]:
            record = mastery.get(item["concept_id"])
            current = None
            if record:
                current = round(
                    float(record.get("mastery_probability") or 0)
                    * retention(record["last_practiced_at"], record["next_review_at"], now),
                    4,
                )
            concepts.append(
                {
                    **item,
                    "current_mastery": current,
                    "band": mastery_band(current).value if current is not None else None,
                }
            )
        return {
            "booster_id": document["_id"],
            "session_id": str(document["session_id"]),
            "title": document["title"],
            "lesson": document["lesson"],
            "key_points": list(document.get("key_points") or []),
            "concepts": concepts,
            "checks": [
                {**_public_check(item), "concept_label": item.get("concept_label") or ""}
                for item in checks
            ],
            "total": len(checks),
            "answered": len(answered),
            "correct": correct,
            "completed": completed,
            "percent": percent,
            "gap_closed": completed and percent >= BOOSTER_PASS_PERCENT,
            "pass_percent": BOOSTER_PASS_PERCENT,
            "created_at": document["created_at"].isoformat()
            if hasattr(document.get("created_at"), "isoformat")
            else None,
        }
