from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.lexinit.schemas.adaptive import AdaptationDecision, ConceptMastery


class AssessmentType(str, Enum):
    MCQ = "mcq"
    TRUE_FALSE = "truefalse"
    ONE_WORD = "oneword"


class AssessmentSubmissionRequest(BaseModel):
    # Kept compatible with the current endpoint. The future v1 attempt endpoint
    # will forbid extra fields and require an idempotency/attempt token.
    model_config = ConfigDict(extra="ignore")

    answers: list[Any]
    module_id: str | None = Field(default=None, min_length=3, max_length=160)


class QuestionFeedback(BaseModel):
    correct: bool
    correct_answer: Any
    explanation: str


class QuestionSnapshot(BaseModel):
    question: str
    selected_answer: Any
    options: list[str] | None = None
    selected_option: str | None = None


class GradingResult(BaseModel):
    score: int
    total: int
    feedback: list[QuestionFeedback]
    question_snapshots: list[QuestionSnapshot]
    incorrect_context: str


class AssessmentSubmissionOutcome(BaseModel):
    submission_id: str
    source_session_id: str
    source_topic: str
    score: int
    total: int
    feedback: list[QuestionFeedback]
    adaptive_topic: str = ""
    adaptive_error: str = ""
    mastery_updates: list[ConceptMastery] = Field(default_factory=list)
    adaptation_decisions: list[AdaptationDecision] = Field(default_factory=list)
    attempt_id: str | None = None

    def public_response(self) -> dict[str, Any]:
        payload = self.model_dump(
            mode="json",
            exclude={"mastery_updates", "adaptation_decisions"},
        )
        payload["mastery_updates"] = [item.public_dict() for item in self.mastery_updates]
        payload["adaptation_decisions"] = [item.public_dict() for item in self.adaptation_decisions]
        return {"success": True, **payload}
