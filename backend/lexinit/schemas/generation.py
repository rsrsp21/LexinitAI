from __future__ import annotations

from enum import Enum

import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class GenerationMode(str, Enum):
    BASIC = "Basic"
    PRO_REASONING = "Pro Reasoning"


class GenerationRequest(BaseModel):
    """Validated input for standard and assessment-driven generation."""

    # Unknown fields are temporarily ignored to preserve the existing frontend
    # contract. Versioned v1 routes will use strict, extra-forbid request models.
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")

    topic: str = Field(min_length=2, max_length=500)
    difflevel: Difficulty
    mode: GenerationMode = GenerationMode.BASIC
    assessment_submission_id: str | None = Field(default=None, max_length=128)
    source_ids: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("difflevel", mode="before")
    @classmethod
    def normalize_difficulty(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("topic")
    @classmethod
    def validate_topic_text(cls, value: str) -> str:
        if not any(character.isalnum() for character in value):
            raise ValueError("Topic must contain a letter or number.")
        if any(unicodedata.category(character).startswith("C") for character in value):
            raise ValueError("Topic contains unsupported hidden or control characters.")
        return value

    @field_validator("source_ids")
    @classmethod
    def validate_source_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Source IDs must be unique.")
        if any(not re.fullmatch(r"[a-f0-9]{24}", item) for item in value):
            raise ValueError("Invalid source ID.")
        return value


class GenerationV1Request(GenerationRequest):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
