from __future__ import annotations

from typing import Protocol

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from backend.lexinit.schemas.adaptive import AdaptationDecision, ConceptMastery, MasteryBand, MasteryEvidence


class AdaptiveLearningRepository(Protocol):
    def add_evidence(self, evidence: MasteryEvidence) -> bool: ...

    def list_evidence(self, user_id: str, concept_id: str) -> list[MasteryEvidence]: ...

    def save_mastery(self, mastery: ConceptMastery) -> None: ...

    def save_decision(self, decision: AdaptationDecision) -> None: ...

    def list_mastery(
        self,
        user_id: str,
        *,
        bands: set[MasteryBand] | None = None,
        limit: int = 100,
    ) -> list[ConceptMastery]: ...


class MongoAdaptiveLearningRepository:
    def __init__(self, *, evidence_collection, mastery_collection, decisions_collection) -> None:
        self._evidence = evidence_collection
        self._mastery = mastery_collection
        self._decisions = decisions_collection

    def add_evidence(self, evidence: MasteryEvidence) -> bool:
        document = evidence.model_dump(mode="python")
        document["_id"] = evidence.evidence_id
        document["user_id"] = ObjectId(evidence.user_id)
        try:
            self._evidence.insert_one(document)
            return True
        except DuplicateKeyError:
            return False

    def list_evidence(self, user_id: str, concept_id: str) -> list[MasteryEvidence]:
        cursor = self._evidence.find(
            {"user_id": ObjectId(user_id), "concept_id": concept_id}
        ).sort([("observed_at", 1), ("_id", 1)])
        result = []
        for document in cursor:
            payload = dict(document)
            payload.pop("_id", None)
            payload["user_id"] = str(payload["user_id"])
            result.append(MasteryEvidence.model_validate(payload))
        return result

    def save_mastery(self, mastery: ConceptMastery) -> None:
        document = mastery.model_dump(mode="python")
        document["user_id"] = ObjectId(mastery.user_id)
        self._mastery.replace_one(
            {"user_id": document["user_id"], "concept_id": mastery.concept_id},
            document,
            upsert=True,
        )

    def save_decision(self, decision: AdaptationDecision) -> None:
        document = decision.model_dump(mode="python")
        document["_id"] = decision.decision_id
        document["user_id"] = ObjectId(decision.user_id)
        try:
            self._decisions.insert_one(document)
        except DuplicateKeyError:
            return

    def list_mastery(
        self,
        user_id: str,
        *,
        bands: set[MasteryBand] | None = None,
        limit: int = 100,
    ) -> list[ConceptMastery]:
        query: dict = {"user_id": ObjectId(user_id)}
        if bands:
            query["band"] = {"$in": [band.value for band in bands]}
        cursor = self._mastery.find(query).sort(
            [("mastery_probability", 1), ("last_practiced_at", -1)]
        ).limit(limit)
        result = []
        for document in cursor:
            payload = dict(document)
            payload.pop("_id", None)
            payload["user_id"] = str(payload["user_id"])
            result.append(ConceptMastery.model_validate(payload))
        return result
