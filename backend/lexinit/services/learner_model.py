"""The learner model across courses and time.

* knowledge map  - every concept the learner has met, with mastery adjusted
                   for forgetting, grouped by course and module
* mastery transfer - a concept already learnt in one course starts a new
                   course with that knowledge instead of from zero
* course goal    - a target date turned into a daily study pace
"""

from __future__ import annotations

import datetime
import hashlib
import math
from typing import Any

from bson import ObjectId

from backend.lexinit.domain.mastery import calculate_mastery
from backend.lexinit.domain.mastery.calculator import mastery_band, retention
from backend.lexinit.repositories.adaptive import AdaptiveLearningRepository
from backend.lexinit.schemas.adaptive import MasteryEvidence
from backend.lexinit.schemas.generation import Difficulty


TRANSFER_EVIDENCE_WEIGHT = 0.5
FINAL_ASSESSMENT_MINUTES = 20
HEAVY_DAILY_MINUTES = 90
MAX_GOAL_DAYS = 365


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _aware(value):
    if isinstance(value, datetime.datetime) and value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value


def _normalize_label(value: Any) -> str:
    return " ".join(str(value or "").casefold().replace("-", " ").split())


# ------------------------------------------------------------- knowledge map


def knowledge_map(db, user_id: ObjectId, *, course_limit: int = 30) -> dict[str, Any]:
    now = utcnow()
    mastery = {item["concept_id"]: item for item in db.concept_mastery.find({"user_id": user_id})}
    courses = []
    totals = {"concepts": 0, "practised": 0, "strong": 0, "fading": 0, "due": 0}
    for session_data in (
        db.sessions.find(
            {"user_id": user_id, "curriculum.modules": {"$exists": True}},
            {"topic": 1, "curriculum": 1, "created_at": 1},
        )
        .sort("created_at", -1)
        .limit(course_limit)
    ):
        modules = []
        for module in (session_data.get("curriculum") or {}).get("modules") or []:
            concepts = []
            for concept in module.get("concepts") or []:
                concept_id = concept.get("concept_id")
                if not concept_id:
                    continue
                record = mastery.get(concept_id)
                item: dict[str, Any] = {
                    "concept_id": concept_id,
                    "label": str(concept.get("name") or concept_id),
                    "prerequisite_ids": list(concept.get("prerequisite_ids") or []),
                    "status": "new",
                    "current_mastery": None,
                    "peak_mastery": None,
                    "retention": None,
                    "band": None,
                    "due": False,
                    "attempts": 0,
                }
                totals["concepts"] += 1
                if record:
                    remembered = retention(record["last_practiced_at"], record["next_review_at"], now)
                    peak = float(record.get("mastery_probability") or 0)
                    current = round(peak * remembered, 4)
                    due = _aware(record["next_review_at"]) <= now
                    band = mastery_band(current).value
                    # "fading": was learnt well, but has slipped a band through forgetting.
                    fading = mastery_band(peak).value in {"proficient", "mastered"} and band in {
                        "weak",
                        "developing",
                    }
                    item.update(
                        {
                            "status": "fading" if fading else band,
                            "current_mastery": current,
                            "peak_mastery": round(peak, 4),
                            "retention": remembered,
                            "band": band,
                            "due": due,
                            "attempts": int(record.get("attempts") or 0),
                            "last_practiced_at": _aware(record["last_practiced_at"]).isoformat(),
                            "next_review_at": _aware(record["next_review_at"]).isoformat(),
                        }
                    )
                    totals["practised"] += 1
                    totals["strong"] += 1 if band in {"proficient", "mastered"} else 0
                    totals["fading"] += 1 if fading else 0
                    totals["due"] += 1 if due else 0
                concepts.append(item)
            if concepts:
                modules.append(
                    {
                        "module_id": module.get("module_id"),
                        "title": str(module.get("title") or "Module"),
                        "concepts": concepts,
                    }
                )
        if modules:
            courses.append(
                {
                    "session_id": str(session_data["_id"]),
                    "topic": str(session_data.get("topic") or "Untitled course"),
                    "modules": modules,
                }
            )
    return {"summary": totals, "courses": courses}


# ---------------------------------------------------------- mastery transfer


def transfer_prior_mastery(
    db,
    repository: AdaptiveLearningRepository,
    user_id: ObjectId,
    session_data: dict[str, Any],
) -> int:
    """Seed a course's concepts from the same-named concepts the learner has
    already practised in other courses. Runs once per course."""
    if session_data.get("mastery_transfer_checked"):
        return 0
    concepts = {
        concept["concept_id"]: str(concept.get("name") or "")
        for module in (session_data.get("curriculum") or {}).get("modules") or []
        for concept in module.get("concepts") or []
        if concept.get("concept_id")
    }
    seeded = 0
    if concepts:
        existing = {
            item["concept_id"]
            for item in db.concept_mastery.find(
                {"user_id": user_id, "concept_id": {"$in": list(concepts)}}, {"concept_id": 1}
            )
        }
        # Concept names come from the other courses' curricula; names stored
        # on older mastery records can be the course topic instead.
        other_names = {
            concept["concept_id"]: str(concept.get("name") or "")
            for other in db.sessions.find(
                {"user_id": user_id, "_id": {"$ne": session_data["_id"]}}, {"curriculum.modules.concepts": 1}
            )
            for module in (other.get("curriculum") or {}).get("modules") or []
            for concept in module.get("concepts") or []
            if concept.get("concept_id")
        }
        by_label: dict[str, dict[str, Any]] = {}
        for record in db.concept_mastery.find({"user_id": user_id, "concept_id": {"$in": list(other_names)}}):
            key = _normalize_label(other_names[record["concept_id"]])
            if not key or int(record.get("attempts") or 0) < 2:
                continue
            best = by_label.get(key)
            if not best or _aware(record["last_practiced_at"]) > _aware(best["last_practiced_at"]):
                by_label[key] = record
        now = utcnow()
        for concept_id, label in concepts.items():
            if concept_id in existing:
                continue
            prior = by_label.get(_normalize_label(label))
            if not prior:
                continue
            current = float(prior.get("mastery_probability") or 0) * retention(
                prior["last_practiced_at"], prior["next_review_at"], now
            )
            # Only carry over a clear signal; the middle band says too little.
            if 0.4 <= current < 0.65:
                continue
            digest = hashlib.sha256(f"{session_data['_id']}|{concept_id}|transfer".encode()).hexdigest()
            evidence = MasteryEvidence(
                evidence_id=f"evidence_{digest[:32]}",
                user_id=str(user_id),
                submission_id=f"transfer:{prior['concept_id']}",
                session_id=str(session_data["_id"]),
                question_id=f"transfer:{concept_id}",
                concept_id=concept_id,
                concept_label=label,
                correct=current >= 0.65,
                difficulty=Difficulty.MEDIUM,
                observed_at=now,
                source_kind="transfer",
                evidence_weight=TRANSFER_EVIDENCE_WEIGHT,
            )
            if repository.add_evidence(evidence):
                repository.save_mastery(calculate_mastery(repository.list_evidence(str(user_id), concept_id)))
                seeded += 1
    db.sessions.update_one(
        {"_id": session_data["_id"], "user_id": user_id},
        {"$set": {"mastery_transfer_checked": True, "mastery_transferred_concepts": seeded}},
    )
    return seeded


# --------------------------------------------------------------- course goal


def set_course_goal(db, user_id: ObjectId, session_id: Any, target_date: datetime.date | None) -> None:
    if target_date is None:
        db.course_goals.delete_one({"user_id": user_id, "session_id": session_id})
        return
    db.course_goals.update_one(
        {"user_id": user_id, "session_id": session_id},
        {
            "$set": {
                "user_id": user_id,
                "session_id": session_id,
                "target_date": target_date.isoformat(),
                "updated_at": utcnow(),
            }
        },
        upsert=True,
    )


def course_goal_plan(db, user_id: ObjectId, session_id: Any, course: dict[str, Any]) -> dict[str, Any] | None:
    """Turn a target date into a daily pace, from what is actually left."""
    record = db.course_goals.find_one({"user_id": user_id, "session_id": session_id})
    if not record:
        return None
    try:
        target = datetime.date.fromisoformat(str(record.get("target_date")))
    except ValueError:
        return None
    today = utcnow().date()
    remaining = 0.0
    for module in course["modules"]:
        if module["status"] == "completed":
            continue
        remaining += float(module.get("estimated_minutes") or 30) * (
            1 - float(module.get("progress_percent") or 0) / 100
        )
    final = course.get("final_assessment") or {}
    if final.get("required") and not final.get("passed"):
        remaining += FINAL_ASSESSMENT_MINUTES
    remaining_minutes = int(math.ceil(remaining))
    days_left = (target - today).days
    study_days = max(1, days_left + 1)  # today counts as a study day
    minutes_per_day = int(math.ceil(remaining_minutes / study_days)) if remaining_minutes else 0
    if course["status"] == "completed":
        status = "done"
    elif days_left < 0:
        status = "overdue"
    elif minutes_per_day > HEAVY_DAILY_MINUTES:
        status = "tight"
    else:
        status = "on_track"
    return {
        "target_date": target.isoformat(),
        "days_left": days_left,
        "remaining_minutes": remaining_minutes,
        "minutes_per_day": minutes_per_day,
        "status": status,
        "focus_module_id": course.get("current_module_id"),
        "focus_module_title": course.get("current_module_title"),
    }


def parse_goal_date(value: Any) -> datetime.date | None:
    """Accept YYYY-MM-DD from today up to a year ahead; None clears the goal."""
    if value in (None, ""):
        return None
    target = datetime.date.fromisoformat(str(value))
    today = utcnow().date()
    if target < today or (target - today).days > MAX_GOAL_DAYS:
        raise ValueError("Choose a date from today up to one year ahead.")
    return target


def backfill_concept_labels(db) -> int:
    """Give mastery records their concept's real name. Older records were
    labelled with the course topic."""
    updated = 0
    for session_data in db.sessions.find(
        {"curriculum.modules": {"$exists": True}, "concept_labels_backfilled": {"$ne": True}},
        {"user_id": 1, "curriculum.modules.concepts": 1},
    ):
        for module in (session_data.get("curriculum") or {}).get("modules") or []:
            for concept in module.get("concepts") or []:
                if not concept.get("concept_id") or not concept.get("name"):
                    continue
                result = db.concept_mastery.update_many(
                    {
                        "user_id": session_data["user_id"],
                        "concept_id": concept["concept_id"],
                        "concept_label": {"$ne": str(concept["name"])[:200]},
                    },
                    {"$set": {"concept_label": str(concept["name"])[:200]}},
                )
                updated += result.modified_count
        db.sessions.update_one(
            {"_id": session_data["_id"]}, {"$set": {"concept_labels_backfilled": True}}
        )
    return updated
