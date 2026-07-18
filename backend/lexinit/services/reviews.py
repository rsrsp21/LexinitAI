from __future__ import annotations

import datetime
import hashlib
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from backend.lexinit.api.errors import ApiError
from backend.lexinit.domain.mastery import calculate_mastery, choose_adaptation
from backend.lexinit.repositories.adaptive import MongoAdaptiveLearningRepository
from backend.lexinit.schemas.adaptive import (
    AdaptationDecision,
    AdaptiveAction,
    ConceptMastery,
    MasteryEvidence,
)
from backend.lexinit.schemas.generation import Difficulty
from backend.lexinit.schemas.learning_loop import ReviewRating


RATING_POLICY = {
    ReviewRating.AGAIN: {"correct": False, "weight": 0.75, "days": 1},
    ReviewRating.HARD: {"correct": True, "weight": 0.35, "days": 2},
    ReviewRating.GOOD: {"correct": True, "weight": 0.65, "days": 7},
    ReviewRating.EASY: {"correct": True, "weight": 0.9, "days": 21},
}


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class ReviewLearningService:
    def __init__(
        self,
        *,
        repository: MongoAdaptiveLearningRepository,
        mastery_collection,
        evidence_collection,
        decisions_collection,
        review_events_collection,
        sessions_collection,
        question_bank_collection,
    ) -> None:
        self._repository = repository
        self._mastery = mastery_collection
        self._evidence = evidence_collection
        self._decisions = decisions_collection
        self._review_events = review_events_collection
        self._sessions = sessions_collection
        self._question_bank = question_bank_collection

    def due_reviews(
        self,
        *,
        user_id: str,
        due_before: datetime.datetime,
        limit: int,
    ) -> list[dict[str, Any]]:
        cursor = self._mastery.find(
            {
                "user_id": ObjectId(user_id),
                "next_review_at": {"$lte": due_before},
            }
        ).sort([("next_review_at", 1), ("mastery_probability", 1)]).limit(limit)
        return [self._review_item(user_id, document) for document in cursor]

    def record_review(
        self,
        *,
        user_id: str,
        concept_id: str,
        rating: ReviewRating,
        idempotency_key: str,
        artifact_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        user_object_id = ObjectId(user_id)
        event_id = f"review_{_hash(user_id, idempotency_key)[:32]}"
        existing = self._review_events.find_one({"_id": event_id, "user_id": user_object_id})
        if existing:
            if existing["concept_id"] != concept_id or existing["rating"] != rating.value:
                raise ApiError(
                    "This idempotency key was already used for a different review.",
                    status_code=409,
                    code="idempotency_conflict",
                )
            return existing["public_result"]

        mastery_document = self._mastery.find_one(
            {"user_id": user_object_id, "concept_id": concept_id}
        )
        if not mastery_document:
            raise ApiError(
                "This concept is not in your learning profile.",
                status_code=404,
                code="mastery_not_found",
            )
        source_session_id = session_id or self._latest_session_id(user_id, concept_id)
        now = utcnow()
        policy = RATING_POLICY[rating]
        evidence = MasteryEvidence(
            evidence_id=f"evidence_{_hash(event_id, concept_id)[:32]}",
            user_id=user_id,
            submission_id=event_id,
            session_id=source_session_id or "review",
            question_id=artifact_id or f"review:{concept_id}",
            concept_id=concept_id,
            concept_label=str(mastery_document.get("concept_label") or concept_id),
            correct=bool(policy["correct"]),
            difficulty=Difficulty(
                str(
                    getattr(
                        mastery_document.get("difficulty_reached") or "easy",
                        "value",
                        mastery_document.get("difficulty_reached") or "easy",
                    )
                )
            ),
            observed_at=now,
            source_kind="flashcard_review",
            evidence_weight=float(policy["weight"]),
        )
        self._repository.add_evidence(evidence)
        all_evidence = self._repository.list_evidence(user_id, concept_id)
        mastery = calculate_mastery(all_evidence)
        mastery.next_review_at = now + datetime.timedelta(days=int(policy["days"]))
        self._repository.save_mastery(mastery)
        decision = choose_adaptation(
            mastery,
            evidence,
            decision_id=f"decision_{_hash(event_id, concept_id)[:32]}",
        )
        self._repository.save_decision(decision)
        result = {
            "event_id": event_id,
            "rating": rating.value,
            "mastery": mastery.public_dict(),
            "next_action": _public_recommendation(mastery, decision),
        }
        try:
            self._review_events.insert_one(
                {
                    "_id": event_id,
                    "user_id": user_object_id,
                    "concept_id": concept_id,
                    "rating": rating.value,
                    "artifact_id": artifact_id,
                    "session_id": source_session_id,
                    "evidence_id": evidence.evidence_id,
                    "decision_id": decision.decision_id,
                    "idempotency_key": idempotency_key,
                    "public_result": result,
                    "created_at": now,
                }
            )
        except DuplicateKeyError:
            stored = self._review_events.find_one({"_id": event_id})
            if stored:
                return stored["public_result"]
            raise
        return result

    def next_best_action(self, *, user_id: str) -> dict[str, Any] | None:
        user_object_id = ObjectId(user_id)
        now = utcnow()
        mastery_document = self._mastery.find_one(
            {"user_id": user_object_id, "next_review_at": {"$lte": now}},
            sort=[("next_review_at", 1), ("mastery_probability", 1)],
        )
        if mastery_document:
            mastery = _mastery_model(mastery_document)
            return {
                "recommendation_id": f"review:{mastery.concept_id}",
                "concept_id": mastery.concept_id,
                "concept_label": mastery.concept_label,
                "action": AdaptiveAction.SPACED_REVIEW.value,
                "target_difficulty": mastery.difficulty_reached.value,
                "reason_codes": ["review_due"],
                "target_concept_ids": [mastery.concept_id],
                "target_objective_ids": [],
                "next_review_at": mastery.next_review_at.isoformat(),
                "can_generate": False,
            }

        mastery_document = self._mastery.find_one(
            {"user_id": user_object_id},
            sort=[("mastery_probability", 1), ("next_review_at", 1)],
        )
        if not mastery_document:
            return None
        mastery = _mastery_model(mastery_document)
        decision_document = self._decisions.find_one(
            {"user_id": user_object_id, "concept_id": mastery.concept_id},
            sort=[("created_at", -1)],
        )
        if decision_document:
            decision = _decision_model(decision_document)
            return _public_recommendation(mastery, decision)
        return {
            "recommendation_id": f"practice:{mastery.concept_id}",
            "concept_id": mastery.concept_id,
            "concept_label": mastery.concept_label,
            "action": AdaptiveAction.TARGETED_PRACTICE.value,
            "target_difficulty": mastery.difficulty_reached.value,
            "reason_codes": ["lowest_current_mastery"],
            "target_concept_ids": [mastery.concept_id],
            "target_objective_ids": [],
            "next_review_at": mastery.next_review_at.isoformat(),
            "can_generate": True,
        }

    def _review_item(self, user_id: str, mastery_document: dict[str, Any]) -> dict[str, Any]:
        mastery = _mastery_model(mastery_document)
        latest_evidence = self._evidence.find_one(
            {"user_id": ObjectId(user_id), "concept_id": mastery.concept_id},
            sort=[("observed_at", -1)],
        )
        session_id = str(latest_evidence.get("session_id")) if latest_evidence else None
        artifact = self._find_review_artifact(user_id, mastery.concept_id, session_id)
        return {
            "review_id": f"review:{mastery.concept_id}",
            "concept_id": mastery.concept_id,
            "concept_label": mastery.concept_label,
            "band": mastery.band.value,
            "mastery_probability": mastery.mastery_probability,
            "next_review_at": mastery.next_review_at.isoformat(),
            "session_id": session_id,
            "artifact": artifact,
        }

    def _find_review_artifact(self, user_id, concept_id, session_id):
        if session_id:
            session_values: list[Any] = [session_id]
            try:
                session_values.append(ObjectId(session_id))
            except Exception:
                pass
            source = self._sessions.find_one(
                {"_id": {"$in": session_values}, "user_id": ObjectId(user_id)}
            )
            if source:
                for card in source.get("flashcards", []):
                    if concept_id in (card.get("concept_ids") or []):
                        return {
                            "artifact_id": card.get("flashcard_id") or card.get("id"),
                            "kind": "flashcard",
                            "prompt": card.get("question") or card.get("q"),
                            "answer": card.get("answer") or card.get("a"),
                        }
        question = self._question_bank.find_one(
            {"user_id": ObjectId(user_id), "concept_ids": concept_id},
            sort=[("created_at", -1)],
        )
        if question:
            return {
                "artifact_id": question["_id"],
                "kind": "recall_prompt",
                "prompt": question["payload"].get("question")
                or question["payload"].get("q"),
                "answer": None,
            }
        return {
            "artifact_id": None,
            "kind": "self_explanation",
            "prompt": f"Explain {concept_id} in your own words.",
            "answer": None,
        }

    def _latest_session_id(self, user_id, concept_id):
        item = self._evidence.find_one(
            {"user_id": ObjectId(user_id), "concept_id": concept_id},
            sort=[("observed_at", -1)],
        )
        return str(item.get("session_id")) if item else None


def _mastery_model(document) -> ConceptMastery:
    payload = dict(document)
    payload.pop("_id", None)
    payload["user_id"] = str(payload["user_id"])
    return ConceptMastery.model_validate(payload)


def _decision_model(document) -> AdaptationDecision:
    payload = dict(document)
    payload.pop("_id", None)
    payload["user_id"] = str(payload["user_id"])
    return AdaptationDecision.model_validate(payload)


def _public_recommendation(mastery, decision):
    return {
        "recommendation_id": decision.decision_id,
        "decision_id": decision.decision_id,
        "concept_id": mastery.concept_id,
        "concept_label": mastery.concept_label,
        "action": decision.action.value,
        "target_difficulty": decision.target_difficulty.value,
        "reason_codes": list(decision.reason_codes),
        "target_concept_ids": list(decision.target_concept_ids or [mastery.concept_id]),
        "target_objective_ids": list(decision.target_objective_ids),
        "next_review_at": mastery.next_review_at.isoformat(),
        "source_submission_id": decision.source_submission_id,
        "can_generate": decision.action is not AdaptiveAction.SPACED_REVIEW,
    }


def _hash(*values):
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()
