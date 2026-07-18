from __future__ import annotations

from enum import Enum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProfileType(str, Enum):
    STUDENT = "student"
    PROFESSIONAL = "professional"
    INDEPENDENT = "independent"


class ProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=80)
    profile_type: ProfileType
    institution_name: str | None = Field(default=None, max_length=120)
    grade_or_class: str | None = Field(default=None, max_length=80)
    organization_name: str | None = Field(default=None, max_length=120)
    professional_role: str | None = Field(default=None, max_length=120)
    work_experience_years: int | None = Field(default=None, ge=0, le=70)

    @model_validator(mode="after")
    def validate_profile_details(self) -> Self:
        if self.profile_type == ProfileType.STUDENT:
            if not self.institution_name:
                raise ValueError("Students must provide their school or college name.")
            if not self.grade_or_class:
                raise ValueError("Students must provide their grade or class.")
        elif self.profile_type == ProfileType.PROFESSIONAL:
            if not self.organization_name:
                raise ValueError("Professionals must provide their organization name.")
            if self.work_experience_years is None:
                raise ValueError("Professionals must provide their work experience.")
        return self
