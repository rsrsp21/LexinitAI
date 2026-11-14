"""Delete a course and everything learnt, attempted or recorded inside it."""

from __future__ import annotations

from typing import Any

from bson import ObjectId

from backend.lexinit.domain.mastery import calculate_mastery
from backend.lexinit.repositories.adaptive import AdaptiveLearningRepository


# Collections whose records belong to one course, keyed by session_id.
COURSE_COLLECTIONS = (
    "assessment_submissions",
    "assessment_attempts",
    "assessment_question_bank",
    "final_assessments",
    "coach_checks",
    "coach_items",
    "course_activity_progress",
    "course_module_unlocks",
    "course_goals",
    "video_progress",
    "video_study_guides",
    "video_retrieval_events",
    "review_events",
)


def delete_course(
    db,
    repository: AdaptiveLearningRepository,
    user_id: ObjectId,
    session_data: dict[str, Any],
) -> dict[str, int]:
    """Remove the course, its attempts and results, its progress, and the
    mastery built from it. The course badge goes with it, because badges are
    derived from completed courses.

    Uploaded source documents are kept: they live in the learner's library and
    can back other courses.
    """
    session_id = session_data["_id"]
    # Some collections store the id as an ObjectId and some as text.
    session_keys = [session_id, str(session_id)]
    counts: dict[str, int] = {}

    curriculum_concepts = [
        concept["concept_id"]
        for module in (session_data.get("curriculum") or {}).get("modules") or []
        for concept in module.get("concepts") or []
        if concept.get("concept_id")
    ]
    evidence_filter = {"user_id": user_id, "session_id": {"$in": session_keys}}
    touched_concepts = set(curriculum_concepts) | set(db.mastery_evidence.distinct("concept_id", evidence_filter))
    counts["mastery_evidence"] = db.mastery_evidence.delete_many(evidence_filter).deleted_count

    removed_mastery = 0
    for concept_id in touched_concepts:
        remaining = repository.list_evidence(str(user_id), concept_id)
        if remaining:
            # The concept is also practised in another course: keep what was
            # learnt there and recalculate without this course's answers.
            repository.save_mastery(calculate_mastery(remaining))
            continue
        removed_mastery += db.concept_mastery.delete_many(
            {"user_id": user_id, "concept_id": concept_id}
        ).deleted_count
        db.adaptation_decisions.delete_many({"user_id": user_id, "concept_id": concept_id})
    counts["concept_mastery"] = removed_mastery

    for name in COURSE_COLLECTIONS:
        counts[name] = db[name].delete_many(
            {"user_id": user_id, "session_id": {"$in": session_keys}}
        ).deleted_count
    counts["generation_runs"] = db.generation_runs.delete_many(
        {"user_id": user_id, "session_id": {"$in": session_keys}}
    ).deleted_count
    counts["sessions"] = db.sessions.delete_one({"_id": session_id, "user_id": user_id}).deleted_count
    return counts
