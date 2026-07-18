from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.lexinit.schemas.assessment import AssessmentType


class StartAssessmentAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_type: AssessmentType
    question_count: int = Field(default=5, ge=1, le=10)
    module_id: str | None = Field(default=None, min_length=3, max_length=160)


class AttemptAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(min_length=8, max_length=160)
    answer: Any


class FinalizeAssessmentAttemptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_token: str = Field(min_length=32, max_length=256)


class ReviewRating(str, Enum):
    AGAIN = "again"
    HARD = "hard"
    GOOD = "good"
    EASY = "easy"


class ReviewEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_id: str = Field(min_length=3, max_length=160)
    rating: ReviewRating
    artifact_id: str | None = Field(default=None, max_length=160)
    session_id: str | None = Field(default=None, max_length=128)
