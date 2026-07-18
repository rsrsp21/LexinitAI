from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_ids: list[str] = Field(min_length=1, max_length=5)
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(default=6, ge=1, le=12)

    @field_validator("source_ids")
    @classmethod
    def unique_source_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Source IDs must be unique.")
        return value
