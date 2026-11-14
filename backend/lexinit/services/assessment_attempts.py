from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from backend.lexinit.api.errors import ApiError
from backend.lexinit.domain.assessment import grade_assessment, questions_for_assessment
from backend.lexinit.schemas.assessment import AssessmentType
from backend.lexinit.schemas.generation import Difficulty


logger = logging.getLogger(__name__)

DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}
# Questions in a reattempt made of fresh questions.
FRESH_ATTEMPT_SIZE = 3
ACTIVE_ATTEMPT_STATUSES = {"active", "ready", "submitting"}


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class AdaptiveAssessmentAttemptService:
    def __init__(
        self,
        *,
        attempts_collection,
        question_bank_collection,
        mastery_collection,
        secret_key: str,
        submissions_collection=None,
        question_refresher=None,
    ) -> None:
        self._attempts = attempts_collection
        self._question_bank = question_bank_collection
        self._mastery = mastery_collection
        self._submissions = submissions_collection
        # Callable(user_id, session_data, module_id, assessment_type, count)
        # returning the course document with fresh questions appended.
        self._question_refresher = question_refresher
        self._secret_key = secret_key.encode("utf-8")

    def start(
        self,
        *,
        user_id: ObjectId,
        requested_session_id: str,
        session_data: dict[str, Any],
        assessment_type: AssessmentType,
        question_count: int,
        idempotency_key: str,
        module_id: str | None = None,
    ) -> dict[str, Any]:
        existing = self._attempts.find_one(
            {"user_id": user_id, "start_idempotency_key": idempotency_key}
        )
        if existing:
            if (
                str(existing["session_id"]) != str(session_data.get("_id", requested_session_id))
                or existing["assessment_type"] != assessment_type.value
                or existing.get("module_id") != module_id
            ):
                raise ApiError(
                    "This idempotency key belongs to a different assessment attempt.",
                    status_code=409,
                    code="idempotency_conflict",
                )
            return self.public_attempt(existing)

        bank_questions = self._ensure_private_question_bank(
            user_id=user_id,
            requested_session_id=requested_session_id,
            session_data=session_data,
            assessment_type=assessment_type,
        )
        if module_id:
            valid_module_ids = {
                str(module.get("module_id"))
                for module in (session_data.get("curriculum") or {}).get("modules", [])
                if module.get("module_id")
            }
            if module_id not in valid_module_ids:
                raise ApiError("Invalid course module.", code="invalid_course_module")
            bank_questions = [
                question for question in bank_questions if question.get("module_id") == module_id
            ]
        # Answers are revealed after an attempt, so a reattempt should use
        # questions the learner has not seen. When none are left, ask for
        # fresh ones; if that is not possible, fall back to reusing questions.
        preferred_ids: list[str] = []
        if module_id:
            seen_ids = self._seen_question_ids(
                user_id=user_id,
                session_id=session_data.get("_id", requested_session_id),
                assessment_type=assessment_type,
                module_id=module_id,
                module_bank=bank_questions,
            )
            unseen = [question for question in bank_questions if question["_id"] not in seen_ids]
            wanted = min(question_count, FRESH_ATTEMPT_SIZE)
            if seen_ids and len(unseen) < wanted and self._question_refresher is not None:
                try:
                    session_data = self._question_refresher(
                        user_id=user_id,
                        session_data=session_data,
                        module_id=module_id,
                        assessment_type=assessment_type,
                        count=wanted - len(unseen),
                    )
                    bank_questions = [
                        question
                        for question in self._ensure_private_question_bank(
                            user_id=user_id,
                            requested_session_id=requested_session_id,
                            session_data=session_data,
                            assessment_type=assessment_type,
                        )
                        if question.get("module_id") == module_id
                    ]
                    unseen = [question for question in bank_questions if question["_id"] not in seen_ids]
                except Exception:
                    logger.warning("assessment_question_refill_failed", exc_info=True)
            if seen_ids and unseen:
                preferred_ids = [question["_id"] for question in unseen]
                bank_questions = unseen
        target_count = min(question_count, len(bank_questions))
        if target_count < 1:
            raise ApiError(
                "This assessment has no available questions.",
                code="assessment_empty",
            )

        first = self._select_next_question(
            user_id=user_id,
            candidates=bank_questions,
            used_ids=set(),
            previous=None,
        )
        attempt_id = ObjectId()
        now = utcnow()
        document = {
            "_id": attempt_id,
            "user_id": user_id,
            "session_id": session_data.get("_id", requested_session_id),
            "source_topic": str(session_data.get("topic") or "Untitled course"),
            "assessment_type": assessment_type.value,
            "module_id": module_id,
            "status": "active",
            "target_count": target_count,
            "answered_count": 0,
            "current_question_id": first["_id"],
            "answers": [],
            "answer_receipts": [],
            "question_sequence": [first["_id"]],
            "preferred_question_ids": preferred_ids,
            "start_idempotency_key": idempotency_key,
            "finalize_idempotency_key": None,
            "submission_id": None,
            "public_result": None,
            "selection_reason": self._selection_reason(first, None),
            "created_at": now,
            "updated_at": now,
            "expires_at": now + datetime.timedelta(hours=2),
        }
        self._attempts.insert_one(document)
        return self.public_attempt(document)

    def get(self, *, attempt_id: str, user_id: ObjectId) -> dict[str, Any]:
        attempt = self._owned_attempt(attempt_id, user_id)
        return self.public_attempt(attempt)

    def answer(
        self,
        *,
        attempt_id: str,
        user_id: ObjectId,
        question_id: str,
        answer: Any,
        idempotency_key: str,
    ) -> dict[str, Any]:
        attempt = self._owned_attempt(attempt_id, user_id)
        self._ensure_not_expired(attempt)
        receipt_hash = _stable_hash(idempotency_key)
        existing_receipt = next(
            (
                receipt
                for receipt in attempt.get("answer_receipts", [])
                if receipt.get("key_hash") == receipt_hash
            ),
            None,
        )
        if existing_receipt:
            if existing_receipt.get("question_id") != question_id:
                raise ApiError(
                    "This idempotency key was already used for another answer.",
                    status_code=409,
                    code="idempotency_conflict",
                )
            return self.public_attempt(attempt)
        if attempt["status"] != "active":
            raise ApiError(
                "This assessment attempt is not accepting answers.",
                status_code=409,
                code="attempt_not_active",
            )
        if attempt.get("current_question_id") != question_id:
            raise ApiError(
                "Submit the currently assigned question.",
                status_code=409,
                code="unexpected_question",
            )

        question = self._question_bank.find_one(
            {"_id": question_id, "user_id": user_id, "session_id": attempt["session_id"]}
        )
        if not question:
            raise ApiError(
                "The assigned question is unavailable.",
                status_code=409,
                code="question_unavailable",
            )
        assessment_type = AssessmentType(attempt["assessment_type"])
        grading = grade_assessment(assessment_type, [question["payload"]], [answer])
        privately_correct = grading.feedback[0].correct
        answer_record = {
            "question_id": question_id,
            "selected_answer": answer,
            "privately_correct": privately_correct,
            "answered_at": utcnow(),
        }
        used_ids = set(attempt.get("question_sequence", []))
        next_question = None
        next_count = int(attempt.get("answered_count", 0)) + 1
        if next_count < int(attempt["target_count"]):
            candidate_query = {
                "user_id": user_id,
                "session_id": attempt["session_id"],
                "assessment_type": attempt["assessment_type"],
                "_id": {"$nin": list(used_ids)},
            }
            if attempt.get("module_id"):
                # Module assessments must only draw from that module's questions.
                candidate_query["module_id"] = attempt["module_id"]
            remaining_preferred = [
                item for item in attempt.get("preferred_question_ids") or [] if item not in used_ids
            ]
            if remaining_preferred:
                candidate_query["_id"] = {"$in": remaining_preferred}
            candidates = list(self._question_bank.find(candidate_query))
            next_question = self._select_next_question(
                user_id=user_id,
                candidates=candidates,
                used_ids=used_ids,
                previous={"question": question, "correct": privately_correct},
            )

        status = "active" if next_question else "ready"
        update: dict[str, Any] = {
            "$push": {
                "answers": answer_record,
                "answer_receipts": {
                    "key_hash": receipt_hash,
                    "question_id": question_id,
                },
            },
            "$set": {
                "answered_count": next_count,
                "status": status,
                "current_question_id": next_question["_id"] if next_question else None,
                "selection_reason": self._selection_reason(next_question, answer_record)
                if next_question
                else "Assessment responses are ready for secure grading.",
                "updated_at": utcnow(),
            },
        }
        if next_question:
            update["$push"]["question_sequence"] = next_question["_id"]
        updated = self._attempts.find_one_and_update(
            {
                "_id": attempt["_id"],
                "user_id": user_id,
                "status": "active",
                "current_question_id": question_id,
            },
            update,
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise ApiError(
                "This answer was already processed. Refresh the attempt.",
                status_code=409,
                code="attempt_state_changed",
            )
        return self.public_attempt(updated)

    def begin_finalization(
        self,
        *,
        attempt_id: str,
        user_id: ObjectId,
        submission_token: str,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[Any]]:
        attempt = self._owned_attempt(attempt_id, user_id)
        self._ensure_not_expired(attempt)
        if not hmac.compare_digest(submission_token, self._submission_token(attempt)):
            raise ApiError(
                "Invalid assessment submission token.",
                status_code=403,
                code="invalid_submission_token",
            )
        if attempt["status"] == "completed":
            if attempt.get("finalize_idempotency_key") != idempotency_key:
                raise ApiError(
                    "This attempt was already submitted.",
                    status_code=409,
                    code="attempt_already_submitted",
                )
            return attempt, [], []
        if attempt["status"] != "ready":
            raise ApiError(
                "Answer every assigned question before submitting.",
                status_code=409,
                code="attempt_not_ready",
            )
        locked = self._attempts.find_one_and_update(
            {"_id": attempt["_id"], "user_id": user_id, "status": "ready"},
            {
                "$set": {
                    "status": "submitting",
                    "finalize_idempotency_key": idempotency_key,
                    "updated_at": utcnow(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not locked:
            raise ApiError(
                "Assessment submission is already in progress.",
                status_code=409,
                code="attempt_submission_in_progress",
            )
        question_ids = [item["question_id"] for item in locked["answers"]]
        documents = {
            item["_id"]: item
            for item in self._question_bank.find(
                {"_id": {"$in": question_ids}, "user_id": user_id}
            )
        }
        if len(documents) != len(question_ids):
            self.reset_finalization(locked["_id"])
            raise ApiError(
                "One or more assessment questions are unavailable.",
                status_code=409,
                code="question_unavailable",
            )
        questions = [
            {
                **documents[question_id]["payload"],
                "bank_question_id": question_id,
                "module_id": documents[question_id]["payload"].get("module_id")
                or documents[question_id].get("module_id"),
            }
            for question_id in question_ids
        ]
        answers = [item["selected_answer"] for item in locked["answers"]]
        return locked, questions, answers

    def complete_finalization(self, attempt_id: ObjectId, outcome: dict[str, Any]) -> None:
        self._attempts.update_one(
            {"_id": attempt_id, "status": "submitting"},
            {
                "$set": {
                    "status": "completed",
                    "submission_id": outcome.get("submission_id"),
                    "public_result": outcome,
                    "current_question_id": None,
                    "updated_at": utcnow(),
                    "completed_at": utcnow(),
                }
            },
        )

    def reset_finalization(self, attempt_id: ObjectId) -> None:
        self._attempts.update_one(
            {"_id": attempt_id, "status": "submitting"},
            {
                "$set": {
                    "status": "ready",
                    "finalize_idempotency_key": None,
                    "updated_at": utcnow(),
                }
            },
        )

    def public_attempt(self, attempt: dict[str, Any]) -> dict[str, Any]:
        current_question = None
        if attempt.get("current_question_id"):
            document = self._question_bank.find_one(
                {
                    "_id": attempt["current_question_id"],
                    "user_id": attempt["user_id"],
                }
            )
            if document:
                current_question = _public_question(document)
        return {
            "attempt_id": str(attempt["_id"]),
            "session_id": str(attempt["session_id"]),
            "source_topic": attempt.get("source_topic") or "Untitled course",
            "assessment_type": attempt["assessment_type"],
            "status": attempt["status"],
            "target_count": int(attempt["target_count"]),
            "answered_count": int(attempt.get("answered_count", 0)),
            "current_question": current_question,
            "selection_reason": attempt.get("selection_reason") or "",
            "submission_token": self._submission_token(attempt),
            "public_result": attempt.get("public_result"),
            "expires_at": _iso(attempt.get("expires_at")),
        }

    def _ensure_private_question_bank(
        self,
        *,
        user_id: ObjectId,
        requested_session_id: str,
        session_data: dict[str, Any],
        assessment_type: AssessmentType,
    ) -> list[dict[str, Any]]:
        questions = questions_for_assessment(session_data, assessment_type)
        session_id = session_data.get("_id", requested_session_id)
        module_order = [
            str(module.get("module_id"))
            for module in (session_data.get("curriculum") or {}).get("modules", [])
            if module.get("module_id")
        ]
        for index, question in enumerate(questions):
            question_id = _private_question_id(
                str(session_id), assessment_type.value, index, question
            )
            document = {
                "_id": question_id,
                "user_id": user_id,
                "session_id": session_id,
                "assessment_type": assessment_type.value,
                "payload": dict(question),
                "concept_ids": _safe_list(question.get("concept_ids")),
                "objective_ids": _safe_list(question.get("objective_ids")),
                "module_id": question.get("module_id")
                or (module_order[index % len(module_order)] if module_order else None),
                "difficulty": _difficulty_value(question.get("difficulty")),
                "created_at": utcnow(),
            }
            self._question_bank.replace_one({"_id": question_id}, document, upsert=True)
        return list(
            self._question_bank.find(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "assessment_type": assessment_type.value,
                }
            )
        )

    def _seen_question_ids(self, *, user_id, session_id, assessment_type, module_id, module_bank):
        if self._submissions is None:
            return set()
        seen: set[str] = set()
        for submission in self._submissions.find(
            {
                "user_id": user_id,
                "session_id": session_id,
                "assessment_type": assessment_type.value,
                "module_id": module_id,
            },
            {"question_refs": 1},
        ):
            ids = [
                item.get("bank_question_id")
                for item in submission.get("question_refs") or []
                if item.get("bank_question_id")
            ]
            if ids:
                seen.update(ids)
            else:
                # Result saved before question tracking: assume the original
                # module questions were all shown.
                seen.update(
                    question["_id"]
                    for question in module_bank
                    if (question.get("payload") or {}).get("generation_kind") != "refill"
                )
        return seen

    def _select_next_question(
        self,
        *,
        user_id: ObjectId,
        candidates: list[dict[str, Any]],
        used_ids: set[str],
        previous: dict[str, Any] | None,
    ) -> dict[str, Any]:
        remaining = [item for item in candidates if item["_id"] not in used_ids]
        if not remaining:
            raise ApiError(
                "No additional adaptive questions are available.",
                status_code=409,
                code="question_bank_exhausted",
            )
        concept_ids = {
            concept_id for item in remaining for concept_id in item.get("concept_ids", [])
        }
        mastery = {
            item["concept_id"]: item
            for item in self._mastery.find(
                {"user_id": user_id, "concept_id": {"$in": list(concept_ids)}}
            )
        }
        previous_question = previous.get("question") if previous else None
        previous_concepts = set(previous_question.get("concept_ids", [])) if previous_question else set()
        previous_rank = (
            DIFFICULTY_ORDER.get(previous_question.get("difficulty"), 1)
            if previous_question
            else 1
        )
        previous_correct = previous.get("correct") if previous else None

        def rank(item):
            item_concepts = item.get("concept_ids", [])
            probability = min(
                (
                    float(mastery.get(concept_id, {}).get("mastery_probability", 0.5))
                    for concept_id in item_concepts
                ),
                default=0.5,
            )
            difficulty_rank = DIFFICULTY_ORDER.get(item.get("difficulty"), 1)
            shared = bool(previous_concepts.intersection(item_concepts))
            if previous_correct is False:
                return (not shared, difficulty_rank > previous_rank, probability, item["_id"])
            if previous_correct is True:
                desired = min(2, previous_rank + 1)
                return (abs(difficulty_rank - desired), probability, item["_id"])
            return (probability, difficulty_rank, item["_id"])

        return min(remaining, key=rank)

    @staticmethod
    def _selection_reason(question, previous):
        if not question:
            return ""
        if previous and not previous.get("privately_correct"):
            return "This question gives you another chance to strengthen the concept."
        if previous and previous.get("privately_correct"):
            return "This question checks the idea in a new way or raises the level."
        return "Starting with a concept that would benefit from more practice."

    def _submission_token(self, attempt: dict[str, Any]) -> str:
        message = f"{attempt['_id']}:{attempt['user_id']}:finalize".encode("utf-8")
        return hmac.new(self._secret_key, message, hashlib.sha256).hexdigest()

    def _owned_attempt(self, attempt_id: str, user_id: ObjectId) -> dict[str, Any]:
        try:
            lookup_id = ObjectId(attempt_id)
        except Exception as exc:
            raise ApiError("Invalid assessment attempt id.", code="invalid_attempt_id") from exc
        attempt = self._attempts.find_one({"_id": lookup_id, "user_id": user_id})
        if not attempt:
            raise ApiError(
                "Assessment attempt not found.",
                status_code=404,
                code="attempt_not_found",
            )
        return attempt

    def _ensure_not_expired(self, attempt):
        expires_at = attempt.get("expires_at")
        if isinstance(expires_at, datetime.datetime):
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
            if expires_at <= utcnow():
                self._attempts.update_one(
                    {"_id": attempt["_id"]},
                    {"$set": {"status": "expired", "updated_at": utcnow()}},
                )
                raise ApiError(
                    "This assessment attempt expired. Start a new attempt.",
                    status_code=410,
                    code="attempt_expired",
                )


def _private_question_id(session_id, assessment_type, index, question):
    raw = f"{session_id}|{assessment_type}|{index}|{question.get('question') or question.get('q') or ''}"
    return f"question_{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _public_question(document):
    payload = document["payload"]
    result = {
        "question_id": document["_id"],
        "question": str(payload.get("question") or payload.get("q") or ""),
        "difficulty": document.get("difficulty", "medium"),
        "concept_ids": list(document.get("concept_ids", [])),
        "objective_ids": list(document.get("objective_ids", [])),
        "module_id": document.get("module_id"),
    }
    if document["assessment_type"] == AssessmentType.MCQ.value:
        result["options"] = list(payload.get("options") or [])
    return result


def _safe_list(value):
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:12]


def _difficulty_value(value):
    try:
        value = getattr(value, "value", value)
        return Difficulty(str(value or "medium").strip().lower()).value
    except ValueError:
        return Difficulty.MEDIUM.value


def _stable_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _iso(value):
    if not isinstance(value, datetime.datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.isoformat()
