from __future__ import annotations

import datetime
from collections import Counter
from typing import Any

from bson import ObjectId


MASTERY_BANDS = ("weak", "developing", "proficient", "mastered")


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _iso(value: Any) -> str | None:
    if not isinstance(value, datetime.datetime):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc).isoformat()


def _percentage(score: Any, total: Any) -> float | None:
    if isinstance(score, bool) or isinstance(total, bool):
        return None
    if not isinstance(score, (int, float)) or not isinstance(total, (int, float)) or total <= 0:
        return None
    return round(max(0, min(100, (float(score) / float(total)) * 100)), 1)


def _assessment_rows(submissions: list[dict]) -> list[dict]:
    rows = []
    for item in submissions:
        percentage = _percentage(item.get("score"), item.get("total"))
        if percentage is None:
            continue
        rows.append(
            {
                "submission_id": str(item.get("_id")),
                "session_id": str(item.get("session_id") or ""),
                "topic": str(item.get("source_topic") or "Untitled course"),
                "assessment_type": str(_value(item.get("assessment_type")) or "assessment"),
                "score": int(item.get("score") or 0),
                "total": int(item.get("total") or 0),
                "percentage": percentage,
                "weak_topic": str(item.get("weak_topic") or ""),
                "created_at": _iso(item.get("created_at")),
            }
        )
    return rows


def _active_days(db, user_id: ObjectId, submissions: list[dict], now: datetime.datetime) -> tuple[int, int]:
    dates = {
        value.date()
        for value in (item.get("created_at") for item in submissions)
        if isinstance(value, datetime.datetime)
    }
    for collection, field in (
        (db.review_events, "created_at"),
        (db.video_progress, "updated_at"),
        (db.sessions, "created_at"),
    ):
        for item in collection.find({"user_id": user_id}, {field: 1}).sort(field, -1).limit(200):
            value = item.get(field)
            if isinstance(value, datetime.datetime):
                dates.add(value.date())

    today = now.date()
    active_days_30 = sum(1 for value in dates if 0 <= (today - value).days < 30)
    cursor = today if today in dates else today - datetime.timedelta(days=1)
    streak = 0
    while cursor in dates:
        streak += 1
        cursor -= datetime.timedelta(days=1)
    return active_days_30, streak


def build_learner_dashboard(db, user_id: str, *, now: datetime.datetime | None = None) -> dict:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    user_object_id = ObjectId(user_id)

    submission_documents = list(
        db.assessment_submissions.find(
            {"user_id": user_object_id},
            {
                "session_id": 1,
                "source_topic": 1,
                "assessment_type": 1,
                "score": 1,
                "total": 1,
                "weak_topic": 1,
                "created_at": 1,
            },
        )
        .sort("created_at", -1)
        .limit(100)
    )
    assessments = _assessment_rows(submission_documents)
    chronological = list(reversed(assessments))
    score_summary = next(
        db.assessment_submissions.aggregate(
            [
                {"$match": {"user_id": user_object_id}},
                {
                    "$group": {
                        "_id": None,
                        "attempts": {"$sum": 1},
                        "score": {"$sum": "$score"},
                        "total": {"$sum": "$total"},
                    }
                },
            ]
        ),
        {},
    )
    assessments_completed = max(0, int(score_summary.get("attempts") or 0))
    total_correct = max(0, int(score_summary.get("score") or 0))
    total_questions = max(0, int(score_summary.get("total") or 0))
    overall_accuracy = round((total_correct / total_questions) * 100, 1) if total_questions else 0.0

    assessment_types = [
        {
            "assessment_type": str(item.get("_id") or "assessment"),
            "attempts": max(0, int(item.get("attempts") or 0)),
            "accuracy": round((int(item.get("score") or 0) / int(item.get("total") or 1)) * 100, 1),
        }
        for item in db.assessment_submissions.aggregate(
            [
                {"$match": {"user_id": user_object_id}},
                {
                    "$group": {
                        "_id": "$assessment_type",
                        "attempts": {"$sum": 1},
                        "score": {"$sum": "$score"},
                        "total": {"$sum": "$total"},
                    }
                },
                {"$sort": {"_id": 1}},
            ]
        )
        if int(item.get("total") or 0) > 0
    ]

    improvement = None
    if len(chronological) >= 4:
        midpoint = len(chronological) // 2
        earlier = chronological[:midpoint]
        recent = chronological[midpoint:]
        improvement = round(
            sum(item["percentage"] for item in recent) / len(recent)
            - sum(item["percentage"] for item in earlier) / len(earlier),
            1,
        )

    mastery_documents = list(
        db.concept_mastery.find(
            {"user_id": user_object_id},
            {
                "concept_id": 1,
                "concept_label": 1,
                "mastery_probability": 1,
                "confidence": 1,
                "band": 1,
                "attempts": 1,
                "correct_attempts": 1,
                "difficulty_reached": 1,
                "misconception_counts": 1,
                "last_practiced_at": 1,
                "next_review_at": 1,
            },
        )
    )
    misconception_labels = {
        str(item.get("misconception_id")): str(item.get("misconception_label") or "").strip()
        for item in db.mastery_evidence.find(
            {
                "user_id": user_object_id,
                "misconception_id": {"$ne": None},
            },
            {"misconception_id": 1, "misconception_label": 1},
        )
        if item.get("misconception_id") and item.get("misconception_label")
    }
    mastery = []
    misconception_counts: Counter[str] = Counter()
    for item in mastery_documents:
        probability = max(0.0, min(1.0, float(item.get("mastery_probability") or 0)))
        band = str(_value(item.get("band")) or "weak")
        misconceptions = {
            str(name): int(count)
            for name, count in (item.get("misconception_counts") or {}).items()
            if isinstance(count, int) and count > 0
        }
        concept_label = str(item.get("concept_label") or item.get("concept_id") or "Concept")
        for misconception_id in misconceptions:
            misconception_labels.setdefault(
                misconception_id,
                f"Review {concept_label}",
            )
        misconception_counts.update(misconceptions)
        mastery.append(
            {
                "concept_id": str(item.get("concept_id") or ""),
                "concept_label": concept_label,
                "mastery_probability": round(probability, 4),
                "confidence": round(max(0.0, min(1.0, float(item.get("confidence") or 0))), 4),
                "band": band if band in MASTERY_BANDS else "weak",
                "attempts": max(0, int(item.get("attempts") or 0)),
                "correct_attempts": max(0, int(item.get("correct_attempts") or 0)),
                "difficulty_reached": str(_value(item.get("difficulty_reached")) or "easy"),
                "last_practiced_at": _iso(item.get("last_practiced_at")),
                "next_review_at": _iso(item.get("next_review_at")),
            }
        )
    mastery.sort(key=lambda item: (item["mastery_probability"], -item["attempts"]))
    mastery_distribution = {band: 0 for band in MASTERY_BANDS}
    for item in mastery:
        mastery_distribution[item["band"]] += 1
    average_mastery = (
        round(sum(item["mastery_probability"] for item in mastery) / len(mastery) * 100, 1)
        if mastery
        else 0.0
    )
    due_reviews = sum(
        1
        for item in mastery_documents
        if isinstance(item.get("next_review_at"), datetime.datetime)
        and item["next_review_at"].replace(tzinfo=item["next_review_at"].tzinfo or datetime.timezone.utc) <= now
    )

    labels = {item["concept_id"]: item["concept_label"] for item in mastery}
    decisions = []
    for item in (
        db.adaptation_decisions.find(
            {"user_id": user_object_id},
            {"concept_id": 1, "action": 1, "target_difficulty": 1, "reason_codes": 1, "created_at": 1},
        )
        .sort("created_at", -1)
        .limit(8)
    ):
        concept_id = str(item.get("concept_id") or "")
        decisions.append(
            {
                "decision_id": str(item.get("_id")),
                "concept_id": concept_id,
                "concept_label": labels.get(concept_id, concept_id.replace("_", " ").title()),
                "action": str(_value(item.get("action")) or "targeted_practice"),
                "target_difficulty": str(_value(item.get("target_difficulty")) or "easy"),
                "reason_codes": [str(value) for value in item.get("reason_codes") or []],
                "created_at": _iso(item.get("created_at")),
            }
        )

    evidence_mix = {
        str(item.get("_id") or "assessment"): int(item.get("count") or 0)
        for item in db.mastery_evidence.aggregate(
            [
                {"$match": {"user_id": user_object_id}},
                {"$group": {"_id": "$source_kind", "count": {"$sum": 1}}},
            ]
        )
    }
    active_days_30, current_streak = _active_days(db, user_object_id, submission_documents, now)

    return {
        "generated_at": now.isoformat(),
        "overview": {
            "overall_accuracy": overall_accuracy,
            "average_mastery": average_mastery,
            "assessments_completed": assessments_completed,
            "questions_answered": total_questions,
            "concepts_tracked": len(mastery),
            "due_reviews": due_reviews,
            "study_sessions": db.sessions.count_documents({"user_id": user_object_id}),
            "videos_started": db.video_progress.count_documents({"user_id": user_object_id}),
            "videos_completed": db.video_progress.count_documents(
                {"user_id": user_object_id, "completed_at": {"$ne": None}}
            ),
            "active_days_30": active_days_30,
            "current_streak": current_streak,
            "improvement_percentage_points": improvement,
        },
        "score_trend": chronological[-12:],
        "recent_assessments": assessments[:8],
        "assessment_types": assessment_types,
        "mastery_distribution": mastery_distribution,
        "focus_concepts": mastery[:6],
        "strong_concepts": list(reversed(mastery[-4:])),
        "top_misconceptions": [
            {
                "misconception": misconception_labels.get(name, "Review this concept"),
                "count": count,
            }
            for name, count in misconception_counts.most_common(5)
        ],
        "evidence_mix": evidence_mix,
        "recent_adaptations": decisions,
    }
