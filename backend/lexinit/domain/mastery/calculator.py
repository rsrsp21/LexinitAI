from __future__ import annotations

from collections import Counter
from datetime import timedelta

from backend.lexinit.schemas.adaptive import ConceptMastery, MasteryBand, MasteryEvidence
from backend.lexinit.schemas.generation import Difficulty


PRIOR_ALPHA = 2.0
PRIOR_BETA = 2.0
DIFFICULTY_WEIGHTS = {
    Difficulty.EASY: 0.8,
    Difficulty.MEDIUM: 1.0,
    Difficulty.HARD: 1.2,
}
DIFFICULTY_ORDER = {
    Difficulty.EASY: 0,
    Difficulty.MEDIUM: 1,
    Difficulty.HARD: 2,
}


def _mastery_band(probability: float) -> MasteryBand:
    if probability < 0.40:
        return MasteryBand.WEAK
    if probability < 0.65:
        return MasteryBand.DEVELOPING
    if probability < 0.85:
        return MasteryBand.PROFICIENT
    return MasteryBand.MASTERED


def _next_review_delay(band: MasteryBand, latest_correct: bool) -> timedelta:
    if not latest_correct:
        return timedelta(days=1)
    return {
        MasteryBand.WEAK: timedelta(days=1),
        MasteryBand.DEVELOPING: timedelta(days=3),
        MasteryBand.PROFICIENT: timedelta(days=7),
        MasteryBand.MASTERED: timedelta(days=14),
    }[band]


def calculate_mastery(evidence: list[MasteryEvidence]) -> ConceptMastery:
    if not evidence:
        raise ValueError("At least one mastery evidence item is required.")

    ordered = sorted(evidence, key=lambda item: (item.observed_at, item.evidence_id))
    user_id = ordered[0].user_id
    concept_id = ordered[0].concept_id
    if any(item.user_id != user_id or item.concept_id != concept_id for item in ordered):
        raise ValueError("Mastery evidence must belong to one user and one concept.")

    alpha = PRIOR_ALPHA
    beta = PRIOR_BETA
    correct_attempts = 0
    correct_difficulties: list[Difficulty] = []
    misconception_counts: Counter[str] = Counter()

    for item in ordered:
        weight = DIFFICULTY_WEIGHTS[item.difficulty] * item.evidence_weight
        if item.correct:
            alpha += weight
            correct_attempts += 1
            correct_difficulties.append(item.difficulty)
        else:
            beta += weight
        if item.misconception_id:
            misconception_counts[item.misconception_id] += 1

    probability = alpha / (alpha + beta)
    band = _mastery_band(probability)
    latest = ordered[-1]
    reached = max(correct_difficulties, key=DIFFICULTY_ORDER.get) if correct_difficulties else Difficulty.EASY

    return ConceptMastery(
        user_id=user_id,
        concept_id=concept_id,
        concept_label=latest.concept_label,
        mastery_probability=round(probability, 4),
        confidence=round(min(0.95, len(ordered) / (len(ordered) + 5)), 4),
        band=band,
        attempts=len(ordered),
        correct_attempts=correct_attempts,
        evidence_count=len(ordered),
        alpha=round(alpha, 4),
        beta=round(beta, 4),
        difficulty_reached=reached,
        misconception_counts=dict(misconception_counts),
        last_practiced_at=latest.observed_at,
        next_review_at=latest.observed_at + _next_review_delay(band, latest.correct),
    )
