from __future__ import annotations

from typing import Any


PERSONALIZATION_VERSION = "learner-context-v1"
PROFILE_TYPES = {"student", "professional", "independent"}


def learner_context_snapshot(user: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return only the minimum profile data useful for learning personalization."""
    if not user:
        return None
    profile_type = str(user.get("profile_type") or "").strip().lower()
    if profile_type not in PROFILE_TYPES:
        return None

    snapshot: dict[str, Any] = {
        "version": PERSONALIZATION_VERSION,
        "profile_type": profile_type,
    }
    if profile_type == "student":
        grade_or_class = str(user.get("grade_or_class") or "").strip()
        if grade_or_class:
            snapshot["grade_or_class"] = grade_or_class[:80]
    elif profile_type == "professional":
        role = str(user.get("professional_role") or "").strip()
        if role:
            snapshot["professional_role"] = role[:120]
        years = user.get("work_experience_years")
        if isinstance(years, int) and not isinstance(years, bool) and 0 <= years <= 70:
            snapshot["work_experience_years"] = years
    return snapshot


def learner_context_instruction(snapshot: dict[str, Any] | None) -> str | None:
    if not snapshot:
        return None

    profile_type = snapshot.get("profile_type")
    if profile_type == "student":
        stage = snapshot.get("grade_or_class")
        description = "a student"
        if stage:
            description += f" who self-reported their current stage as {stage}"
    elif profile_type == "professional":
        role = snapshot.get("professional_role")
        years = snapshot.get("work_experience_years")
        description = "a professional learner"
        if isinstance(role, str) and role:
            description += f" working as {role}"
        if isinstance(years, int):
            description += f" with {years} years of work experience"
    elif profile_type == "independent":
        description = "an independent learner"
    else:
        return None

    return (
        f"The learner is {description}. Use this only as a soft preference for explanation "
        "style and relatable examples. Never remove advanced material, lower the requested "
        "level, or refuse a topic because of this profile. The learner's explicit topic and "
        "chosen difficulty always override the profile."
    )
