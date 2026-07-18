from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.lexinit.schemas.generation import Difficulty


class KnowledgeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    term: str = Field(min_length=1, max_length=120)
    definition: str = Field(min_length=3, max_length=500)
    concept_ids: list[str] = Field(default_factory=list, max_length=5)


class ModuleKnowledgePack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_pack_id: str
    curriculum_id: str
    module_id: str
    module_title: str = Field(min_length=2, max_length=120)
    difficulty: Difficulty
    concept_ids: list[str] = Field(min_length=1, max_length=5)
    objective_ids: list[str] = Field(min_length=1, max_length=5)
    required_concepts: list[str] = Field(min_length=1, max_length=8)
    definitions: list[KnowledgeDefinition] = Field(default_factory=list, max_length=8)
    important_facts: list[str] = Field(min_length=2, max_length=10)
    examples: list[str] = Field(default_factory=list, max_length=6)
    common_mistakes: list[str] = Field(default_factory=list, max_length=6)
    difficulty_boundaries: list[str] = Field(default_factory=list, max_length=6)
    video_search_terms: list[str] = Field(min_length=2, max_length=8)
    video_exclusions: list[str] = Field(default_factory=list, max_length=8)
    source_references: list[str] = Field(default_factory=list, max_length=20)
    schema_version: int = 1
    prompt_version: str = "knowledge-pack-v1"


class CourseKnowledgePacks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    curriculum_id: str
    packs: list[ModuleKnowledgePack] = Field(min_length=5, max_length=5)
    schema_version: int = 1
    prompt_version: str = "knowledge-pack-v1"

    @model_validator(mode="after")
    def validate_pack_references(self):
        if len({pack.module_id for pack in self.packs}) != len(self.packs):
            raise ValueError("Knowledge packs must have unique module IDs.")
        if any(pack.curriculum_id != self.curriculum_id for pack in self.packs):
            raise ValueError("Every knowledge pack must reference its curriculum.")
        return self
