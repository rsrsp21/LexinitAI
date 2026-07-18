from __future__ import annotations

from typing import Any, Protocol


class AssessmentSubmissionRepository(Protocol):
    def insert(self, submission: dict[str, Any]) -> None: ...

    def set_adaptive_result(self, submission_id: Any, result: dict[str, Any]) -> None: ...


class MongoAssessmentSubmissionRepository:
    def __init__(self, collection) -> None:
        self._collection = collection

    def insert(self, submission: dict[str, Any]) -> None:
        self._collection.insert_one(submission)

    def set_adaptive_result(self, submission_id: Any, result: dict[str, Any]) -> None:
        self._collection.update_one({"_id": submission_id}, {"$set": {"adaptive_result": result}})
