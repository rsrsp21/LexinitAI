from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VideoPlaybackState(str, Enum):
    PLAYING = "playing"
    PAUSED = "paused"
    ENDED = "ended"


class VideoProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position_seconds: float = Field(ge=0, le=86_400)
    duration_seconds: float = Field(gt=0, le=86_400)
    state: VideoPlaybackState

    @model_validator(mode="after")
    def position_must_fit_duration(self):
        if self.position_seconds > self.duration_seconds + 5:
            raise ValueError("Playback position cannot exceed video duration.")
        return self


class VideoRetrievalCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guide_id: str = Field(min_length=12, max_length=128)
    answers: list[str] = Field(min_length=1, max_length=5)


class VideoRetrievalQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=8, max_length=300)
    expected_answer: str = Field(min_length=1, max_length=240)
    answer_keywords: list[str] = Field(min_length=1, max_length=8)
    explanation: str = Field(min_length=8, max_length=400)


class VideoKeyMoment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_seconds: float = Field(ge=0, le=86_400)
    note: str = Field(min_length=8, max_length=240)


class VideoStudyGuideContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_points: list[str] = Field(min_length=3, max_length=8)
    key_moments: list[VideoKeyMoment] = Field(default_factory=list, max_length=6)
    retrieval_questions: list[VideoRetrievalQuestion] = Field(min_length=2, max_length=3)
