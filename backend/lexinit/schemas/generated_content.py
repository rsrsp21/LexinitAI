from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _ReferencedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_ids: list[str] = Field(default_factory=list, max_length=5)
    objective_ids: list[str] = Field(default_factory=list, max_length=5)


class FlashcardDraft(_ReferencedItem):
    question: str = Field(min_length=3, max_length=300)
    answer: str = Field(min_length=1, max_length=300)


class FlashcardSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flashcards: list[FlashcardDraft] = Field(min_length=10, max_length=10)


class MCQMisconception(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_index: int = Field(ge=0, le=3)
    misconception: str = Field(min_length=3, max_length=300)


class MCQDraft(_ReferencedItem):
    question: str = Field(min_length=5, max_length=500)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_option_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=3, max_length=1000)
    misconceptions: list[MCQMisconception] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def validate_options(self):
        normalized = [option.strip().casefold() for option in self.options]
        if any(not option for option in normalized) or len(normalized) != len(set(normalized)):
            raise ValueError("MCQ options must be non-empty and unique.")
        misconception_indexes = [item.option_index for item in self.misconceptions]
        if self.correct_option_index in misconception_indexes:
            raise ValueError("The correct option cannot be mapped to a misconception.")
        if len(misconception_indexes) != len(set(misconception_indexes)):
            raise ValueError("Each incorrect option can have at most one misconception.")
        return self


class MCQSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[MCQDraft] = Field(min_length=10, max_length=10)


class TrueFalseDraft(_ReferencedItem):
    question: str = Field(min_length=5, max_length=500)
    answer: bool
    explanation: str = Field(min_length=3, max_length=1000)
    misconception_if_wrong: str | None = Field(default=None, max_length=300)


class TrueFalseSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[TrueFalseDraft] = Field(min_length=10, max_length=10)


class OneWordDraft(_ReferencedItem):
    question: str = Field(min_length=5, max_length=500)
    answer: str = Field(min_length=1, max_length=100)
    explanation: str = Field(min_length=3, max_length=1000)
    misconception_if_wrong: str | None = Field(default=None, max_length=300)

    @field_validator("answer")
    @classmethod
    def answer_must_be_one_token(cls, value: str) -> str:
        cleaned = value.strip()
        if not re.fullmatch(r"[\w-]+", cleaned, flags=re.UNICODE):
            raise ValueError("One-word answers may contain one word or a hyphenated word.")
        return cleaned


class OneWordSet(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[OneWordDraft] = Field(min_length=10, max_length=10)
