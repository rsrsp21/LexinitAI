from __future__ import annotations

import datetime
import hashlib
import json
import uuid
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument

from backend.extensions import mongo
from backend.lexinit.api.errors import ApiError


ACTIVE_STATUSES = {"queued", "running", "repairing", "saving"}
TERMINAL_STATUSES = {"completed", "cancelled", "failed"}


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def generation_fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_generation_run(
    *,
    user_id: str,
    topic: str,
    original_topic: str,
    difficulty_level: str,
    mode: str,
    model_name: str | None,
    force_new: bool,
    regenerated_from: str | None,
    version: int,
    adaptive_source: dict[str, Any] | None,
    idempotency_key: str,
    source_grounding: dict[str, Any] | None = None,
    learner_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    collection = mongo.db.generation_runs
    user_object_id = ObjectId(user_id)
    fingerprint = generation_fingerprint(
        {
            "topic": topic,
            "difficulty_level": difficulty_level,
            "mode": mode,
            "force_new": force_new,
            "regenerated_from": regenerated_from,
            "version": version,
            "adaptive_source": adaptive_source,
            "source_ids": (source_grounding or {}).get("source_ids", []),
            "learner_context": learner_context,
        }
    )
    existing = collection.find_one(
        {"user_id": user_object_id, "idempotency_key": idempotency_key}
    )
    if existing:
        if existing.get("input_fingerprint") != fingerprint:
            raise ApiError(
                "This idempotency key was already used for a different generation request.",
                status_code=409,
                code="idempotency_conflict",
            )
        return existing, False

    now = utcnow()
    run_id = uuid.uuid4().hex
    document = {
        "_id": run_id,
        "user_id": user_object_id,
        "topic": topic,
        "original_topic": original_topic,
        "difficulty_level": difficulty_level,
        "mode": mode,
        "model_name": model_name,
        "force_new": force_new,
        "regenerated_from": regenerated_from,
        "adaptive_source": adaptive_source,
        "source_grounding": source_grounding,
        "learner_context": learner_context,
        "version": version,
        "idempotency_key": idempotency_key,
        "input_fingerprint": fingerprint,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "message": "Course creation queued.",
        "session_id": None,
        "target_session_id": ObjectId(),
        "error": None,
        "attempt": 1,
        "max_attempts": 3,
        "cancel_requested": False,
        "completed_steps": [],
        "failed_steps": [],
        "checkpoints": {},
        "lease_owner": None,
        "lease_expires_at": None,
        "created_at": now,
        "started_at": None,
        "completed_at": None,
        "updated_at": now,
    }
    try:
        collection.insert_one(document)
        return document, True
    except Exception:
        existing = collection.find_one(
            {"user_id": user_object_id, "idempotency_key": idempotency_key}
        )
        if existing:
            return existing, False
        raise


def get_generation_run(run_id: str, user_id: str | None = None) -> dict[str, Any] | None:
    query: dict[str, Any] = {"_id": run_id}
    if user_id:
        query["user_id"] = ObjectId(user_id)
    return mongo.db.generation_runs.find_one(query)


def list_active_generation_runs(user_id: str) -> list[dict[str, Any]]:
    return list(
        mongo.db.generation_runs.find(
            {"user_id": ObjectId(user_id), "status": {"$in": sorted(ACTIVE_STATUSES)}}
        ).sort("updated_at", -1)
    )


def claim_generation_run(run_id: str, owner: str, lease_seconds: int) -> dict[str, Any] | None:
    now = utcnow()
    lease_expires_at = now + datetime.timedelta(seconds=lease_seconds)
    return mongo.db.generation_runs.find_one_and_update(
        {
            "_id": run_id,
            "status": {"$in": ["queued", "running", "repairing", "saving"]},
            "cancel_requested": {"$ne": True},
            "$or": [
                {"lease_expires_at": None},
                {"lease_expires_at": {"$exists": False}},
                {"lease_expires_at": {"$lte": now}},
                {"lease_owner": owner},
            ],
        },
        {
            "$set": {
                "lease_owner": owner,
                "lease_expires_at": lease_expires_at,
                "updated_at": now,
                "started_at": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )


def update_generation_run(run_id: str, **changes: Any) -> None:
    changes["updated_at"] = utcnow()
    mongo.db.generation_runs.update_one({"_id": run_id}, {"$set": changes})


def complete_step(run_id: str, step: str, checkpoint: Any | None = None) -> None:
    update: dict[str, Any] = {
        "$addToSet": {"completed_steps": step},
        "$pull": {"failed_steps": step},
        "$set": {"updated_at": utcnow()},
    }
    if checkpoint is not None:
        update["$set"][f"checkpoints.{step}"] = checkpoint
    mongo.db.generation_runs.update_one({"_id": run_id}, update)


def mark_step_failed(run_id: str, step: str) -> None:
    mongo.db.generation_runs.update_one(
        {"_id": run_id},
        {
            "$addToSet": {"failed_steps": step},
            "$set": {"updated_at": utcnow()},
        },
    )


def request_generation_cancellation(run_id: str, user_id: str) -> dict[str, Any] | None:
    run = get_generation_run(run_id, user_id)
    if not run:
        return None
    if run["status"] in TERMINAL_STATUSES:
        return run
    now = utcnow()
    changes: dict[str, Any] = {
        "cancel_requested": True,
            "message": "Cancellation requested.",
        "updated_at": now,
    }
    if run["status"] == "queued":
        changes.update(
            {
                "status": "cancelled",
            "message": "Course creation cancelled.",
                "completed_at": now,
            }
        )
    return mongo.db.generation_runs.find_one_and_update(
        {"_id": run_id, "user_id": ObjectId(user_id)},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )


def prepare_generation_retry(run_id: str, user_id: str) -> dict[str, Any] | None:
    run = get_generation_run(run_id, user_id)
    if not run or run["status"] != "failed":
        return None
    if not (run.get("error") or {}).get("retryable", True):
        return None
    if int(run.get("attempt", 1)) >= int(run.get("max_attempts", 3)):
        return None
    return mongo.db.generation_runs.find_one_and_update(
        {"_id": run_id, "user_id": ObjectId(user_id), "status": "failed"},
        {
            "$set": {
                "status": "repairing",
            "message": "Continuing course creation from saved progress.",
                "error": None,
                "cancel_requested": False,
                "lease_owner": None,
                "lease_expires_at": None,
                "completed_at": None,
                "updated_at": utcnow(),
            },
            "$inc": {"attempt": 1},
        },
        return_document=ReturnDocument.AFTER,
    )


def serialize_generation_run(run: dict[str, Any]) -> dict[str, Any]:
    error = run.get("error")
    status = run.get("status", "queued")
    return {
        "id": run["_id"],
        "status": status,
        "stage": run.get("stage", "queued"),
        "progress": int(run.get("progress", 0)),
        "message": run.get("message") or "",
        "session_id": run.get("session_id"),
        "error": error,
        "topic": run.get("topic"),
        "difficulty_level": run.get("difficulty_level"),
        "mode": run.get("mode"),
        "version": run.get("version"),
        "attempt": run.get("attempt", 1),
        "max_attempts": run.get("max_attempts", 3),
        "completed_steps": run.get("completed_steps", []),
        "failed_steps": run.get("failed_steps", []),
        "can_cancel": status in ACTIVE_STATUSES and not run.get("cancel_requested"),
        "can_retry": status == "failed"
        and (error or {}).get("retryable", True)
        and int(run.get("attempt", 1)) < int(run.get("max_attempts", 3)),
        "created_at": _iso(run.get("created_at")),
        "updated_at": _iso(run.get("updated_at")),
    }


def recoverable_generation_run_ids() -> list[str]:
    now = utcnow()
    cursor = mongo.db.generation_runs.find(
        {
            "status": {"$in": ["queued", "running", "repairing", "saving"]},
            "cancel_requested": {"$ne": True},
            "$or": [
                {"lease_expires_at": None},
                {"lease_expires_at": {"$exists": False}},
                {"lease_expires_at": {"$lte": now}},
            ],
        },
        {"_id": 1},
    )
    return [document["_id"] for document in cursor]


def _iso(value: Any) -> str | None:
    if not isinstance(value, datetime.datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.isoformat()
