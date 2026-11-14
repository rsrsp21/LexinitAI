"""Concept mastery estimate.

Mastery is a Beta-Bernoulli estimate built from weighted evidence. Each
observation adds weight to "knows it" (alpha) or "does not know it" (beta).
The weight reflects how much that observation actually tells us:

* Difficulty is asymmetric. Getting a hard question right is strong evidence
  of knowing; getting an easy one wrong is strong evidence of a gap.
* Guessable formats count for less when correct. A right True/False answer is
  half luck, a recalled one-word answer is not.
* Seeing the same question again soon after its answer was shown mostly tests
  memory of the answer, so a repeat correct answer counts for less.
* Old evidence fades. Recent answers describe the learner better than answers
  from two months ago.

Forgetting between practice sessions is modelled separately by
``retention`` / ``current_mastery``, which are applied when mastery is read.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from backend.lexinit.schemas.adaptive import ConceptMastery, MasteryBand, MasteryEvidence
from backend.lexinit.schemas.generation import Difficulty


ALGORITHM_VERSION = 2

PRIOR_ALPHA = 2.0
PRIOR_BETA = 2.0

CORRECT_DIFFICULTY_WEIGHTS = {
    Difficulty.EASY: 0.75,
    Difficulty.MEDIUM: 1.0,
    Difficulty.HARD: 1.25,
}
INCORRECT_DIFFICULTY_WEIGHTS = {
    Difficulty.EASY: 1.25,
    Difficulty.MEDIUM: 1.0,
    Difficulty.HARD: 0.75,
}
DIFFICULTY_ORDER = {
    Difficulty.EASY: 0,
    Difficulty.MEDIUM: 1,
    Difficulty.HARD: 2,
}

# Evidence loses half its weight every this many days.
EVIDENCE_HALF_LIFE_DAYS = 45.0

# A correct answer to a question seen recently counts for less.
REPEAT_WITHIN_DAY_FACTOR = 0.35
REPEAT_WITHIN_WEEK_FACTOR = 0.6
REPEAT_SOURCE_KINDS = {"assessment", "practice", "final_assessment"}

# Effective evidence needed before the estimate is treated as reliable.
CONFIDENCE_HALF_POINT = 3.0
MIN_RELIABLE_CONFIDENCE = 0.3

# Retention is 90% when a review falls due (FSRS-style power curve).
RETENTION_AT_DUE = 0.9


def mastery_band(probability: float) -> MasteryBand:
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


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def evidence_weight(
    item: MasteryEvidence,
    *,
    as_of: datetime,
    previous_exposure: datetime | None,
) -> float:
    """How much one observation moves the estimate."""
    if item.correct:
        weight = CORRECT_DIFFICULTY_WEIGHTS[item.difficulty] * (1.0 - item.guess_probability)
        if previous_exposure is not None and item.source_kind in REPEAT_SOURCE_KINDS:
            gap = _aware(item.observed_at) - _aware(previous_exposure)
            if gap < timedelta(days=1):
                weight *= REPEAT_WITHIN_DAY_FACTOR
            elif gap < timedelta(days=7):
                weight *= REPEAT_WITHIN_WEEK_FACTOR
    else:
        weight = INCORRECT_DIFFICULTY_WEIGHTS[item.difficulty]

    age_days = max(0.0, (_aware(as_of) - _aware(item.observed_at)).total_seconds() / 86_400)
    recency = 0.5 ** (age_days / EVIDENCE_HALF_LIFE_DAYS)
    return weight * item.evidence_weight * recency


def calculate_mastery(
    evidence: list[MasteryEvidence],
    *,
    as_of: datetime | None = None,
) -> ConceptMastery:
    if not evidence:
        raise ValueError("At least one mastery evidence item is required.")

    ordered = sorted(evidence, key=lambda item: (item.observed_at, item.evidence_id))
    user_id = ordered[0].user_id
    concept_id = ordered[0].concept_id
    if any(item.user_id != user_id or item.concept_id != concept_id for item in ordered):
        raise ValueError("Mastery evidence must belong to one user and one concept.")

    latest = ordered[-1]
    reference = as_of or latest.observed_at

    alpha = PRIOR_ALPHA
    beta = PRIOR_BETA
    correct_attempts = 0
    correct_difficulties: list[Difficulty] = []
    misconception_counts: Counter[str] = Counter()
    last_seen: dict[str, datetime] = {}

    for item in ordered:
        weight = evidence_weight(
            item,
            as_of=reference,
            previous_exposure=last_seen.get(item.question_id),
        )
        last_seen[item.question_id] = item.observed_at
        if item.correct:
            alpha += weight
            correct_attempts += 1
            correct_difficulties.append(item.difficulty)
        else:
            beta += weight
        if item.misconception_id:
            misconception_counts[item.misconception_id] += 1

    probability = alpha / (alpha + beta)
    band = mastery_band(probability)
    effective_evidence = (alpha + beta) - (PRIOR_ALPHA + PRIOR_BETA)
    confidence = min(0.95, effective_evidence / (effective_evidence + CONFIDENCE_HALF_POINT))
    reached = max(correct_difficulties, key=DIFFICULTY_ORDER.get) if correct_difficulties else Difficulty.EASY

    return ConceptMastery(
        user_id=user_id,
        concept_id=concept_id,
        concept_label=latest.concept_label,
        mastery_probability=round(probability, 4),
        confidence=round(confidence, 4),
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
        algorithm_version=ALGORITHM_VERSION,
    )


def retention(last_practiced_at: datetime, next_review_at: datetime, now: datetime) -> float:
    """Estimated chance the learner still recalls the concept at ``now``.

    The scheduled review interval is treated as memory stability: retention is
    1.0 right after practice, 0.9 when the review falls due, and keeps
    dropping slowly after that.
    """
    stability_days = max(
        0.5,
        (_aware(next_review_at) - _aware(last_practiced_at)).total_seconds() / 86_400,
    )
    elapsed_days = max(0.0, (_aware(now) - _aware(last_practiced_at)).total_seconds() / 86_400)
    factor = (1 / RETENTION_AT_DUE) - 1
    return round(1 / (1 + factor * elapsed_days / stability_days), 4)


def current_mastery(mastery: ConceptMastery, now: datetime) -> float:
    """Mastery adjusted for forgetting since the concept was last practised."""
    return round(
        mastery.mastery_probability
        * retention(mastery.last_practiced_at, mastery.next_review_at, now),
        4,
    )
