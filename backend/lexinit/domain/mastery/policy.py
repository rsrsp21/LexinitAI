from __future__ import annotations

from backend.lexinit.schemas.adaptive import (
    AdaptationDecision,
    AdaptiveAction,
    ConceptMastery,
    MasteryBand,
    MasteryEvidence,
)
from backend.lexinit.schemas.generation import Difficulty


NEXT_DIFFICULTY = {
    Difficulty.EASY: Difficulty.MEDIUM,
    Difficulty.MEDIUM: Difficulty.HARD,
    Difficulty.HARD: Difficulty.HARD,
}


def choose_adaptation(
    mastery: ConceptMastery,
    latest_evidence: MasteryEvidence,
    *,
    decision_id: str,
    target_objective_ids: list[str] | None = None,
) -> AdaptationDecision:
    reason_codes: list[str]

    repeated_misconception = (
        latest_evidence.misconception_id
        and mastery.misconception_counts.get(latest_evidence.misconception_id, 0) >= 2
    )
    if repeated_misconception:
        action = AdaptiveAction.MISCONCEPTION_CORRECTION
        target_difficulty = Difficulty.EASY
        reason_codes = ["repeated_misconception", "incorrect_response"]
        target_concept_ids = [mastery.concept_id]
    elif not latest_evidence.correct and latest_evidence.prerequisite_concept_ids:
        action = AdaptiveAction.PREREQUISITE_REMEDIATION
        target_difficulty = Difficulty.EASY
        reason_codes = ["incorrect_response", "prerequisite_available"]
        target_concept_ids = list(latest_evidence.prerequisite_concept_ids)
    elif mastery.band is MasteryBand.WEAK:
        action = AdaptiveAction.WEAK_TOPIC_REMEDIATION
        target_difficulty = Difficulty.EASY
        reason_codes = ["mastery_below_0_40"]
        target_concept_ids = [mastery.concept_id]
    elif mastery.band is MasteryBand.DEVELOPING:
        action = AdaptiveAction.TARGETED_PRACTICE
        target_difficulty = latest_evidence.difficulty
        reason_codes = ["mastery_developing"]
        target_concept_ids = [mastery.concept_id]
    elif mastery.band is MasteryBand.PROFICIENT:
        action = AdaptiveAction.APPLICATION_PRACTICE
        target_difficulty = latest_evidence.difficulty
        reason_codes = ["mastery_proficient"]
        target_concept_ids = [mastery.concept_id]
    elif latest_evidence.difficulty is not Difficulty.HARD:
        action = AdaptiveAction.DIFFICULTY_PROGRESSION
        target_difficulty = NEXT_DIFFICULTY[latest_evidence.difficulty]
        reason_codes = ["mastery_above_0_85", "difficulty_can_increase"]
        target_concept_ids = [mastery.concept_id]
    else:
        action = AdaptiveAction.SPACED_REVIEW
        target_difficulty = Difficulty.HARD
        reason_codes = ["mastery_above_0_85", "maximum_difficulty_reached"]
        target_concept_ids = [mastery.concept_id]

    return AdaptationDecision(
        decision_id=decision_id,
        user_id=mastery.user_id,
        concept_id=mastery.concept_id,
        action=action,
        target_difficulty=target_difficulty,
        reason_codes=reason_codes,
        evidence_ids=[latest_evidence.evidence_id],
        source_submission_id=latest_evidence.submission_id,
        target_concept_ids=target_concept_ids,
        target_objective_ids=list(target_objective_ids or []),
        created_at=latest_evidence.observed_at,
    )
