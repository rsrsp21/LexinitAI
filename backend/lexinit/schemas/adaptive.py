from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from backend.lexinit.schemas.generation import Difficulty


class MasteryBand(str, Enum):
    WEAK = "weak"
    DEVELOPING = "developing"
    PROFICIENT = "proficient"
    MASTERED = "mastered"


class AdaptiveAction(str, Enum):
    PREREQUISITE_REMEDIATION = "prerequisite_remediation"
    MISCONCEPTION_CORRECTION = "misconception_correction"
    WEAK_TOPIC_REMEDIATION = "weak_topic_remediation"
    TARGETED_PRACTICE = "targeted_practice"
    APPLICATION_PRACTICE = "application_practice"
    DIFFICULTY_PROGRESSION = "difficulty_progression"
    SPACED_REVIEW = "spaced_review"


class MasteryEvidence(BaseModel):
    evidence_id: str
    user_id: str
    submission_id: str
    session_id: str
    question_id: str
    concept_id: str
    concept_label: str
    correct: bool
    difficulty: Difficulty
    misconception_id: str | None = None
    misconception_label: str | None = None
    prerequisite_concept_ids: list[str] = Field(default_factory=list)
    observed_at: datetime
    source_kind: str = "assessment"
    evidence_weight: float = Field(default=1.0, gt=0, le=1.0)
    evidence_version: int = 1


class ConceptMastery(BaseModel):
    user_id: str
    concept_id: str
    concept_label: str
    mastery_probability: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    band: MasteryBand
    attempts: int
    correct_attempts: int
    evidence_count: int
    alpha: float
    beta: float
    difficulty_reached: Difficulty
    misconception_counts: dict[str, int] = Field(default_factory=dict)
    last_practiced_at: datetime
    next_review_at: datetime
    algorithm_version: int = 1

    def public_dict(self) -> dict:
        return {
            "concept_id": self.concept_id,
            "concept_label": self.concept_label,
            "mastery_probability": self.mastery_probability,
            "confidence": self.confidence,
            "band": self.band.value,
            "attempts": self.attempts,
            "correct_attempts": self.correct_attempts,
            "difficulty_reached": self.difficulty_reached.value,
            "misconception_counts": dict(self.misconception_counts),
            "last_practiced_at": self.last_practiced_at.isoformat(),
            "next_review_at": self.next_review_at.isoformat(),
        }


class AdaptationDecision(BaseModel):
    decision_id: str
    user_id: str
    concept_id: str
    action: AdaptiveAction
    target_difficulty: Difficulty
    reason_codes: list[str]
    evidence_ids: list[str]
    source_submission_id: str
    target_concept_ids: list[str] = Field(default_factory=list)
    target_objective_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    policy_version: int = 1

    def public_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "concept_id": self.concept_id,
            "action": self.action.value,
            "target_difficulty": self.target_difficulty.value,
            "reason_codes": list(self.reason_codes),
            "source_submission_id": self.source_submission_id,
            "target_concept_ids": list(self.target_concept_ids),
            "target_objective_ids": list(self.target_objective_ids),
            "created_at": self.created_at.isoformat(),
        }


class AdaptiveUpdateResult(BaseModel):
    mastery_updates: list[ConceptMastery] = Field(default_factory=list)
    decisions: list[AdaptationDecision] = Field(default_factory=list)


class WeakTopicAnalysis(BaseModel):
    main_topic: str = Field(min_length=2, max_length=120)
    related_subtopics: list[str] = Field(min_length=1, max_length=3)
