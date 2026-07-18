from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.lexinit.schemas.generation import Difficulty


class Concept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    concept_id: str
    name: str = Field(min_length=2, max_length=120)
    prerequisite_ids: list[str] = Field(default_factory=list, max_length=8)
    difficulty: Difficulty


class LearningObjective(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective_id: str
    description: str = Field(min_length=8, max_length=240)
    concept_ids: list[str] = Field(min_length=1, max_length=5)


class CurriculumModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str
    title: str = Field(min_length=2, max_length=120)
    concepts: list[Concept] = Field(min_length=1, max_length=5)
    learning_objectives: list[LearningObjective] = Field(min_length=1, max_length=5)
    common_misconceptions: list[str] = Field(default_factory=list, max_length=5)
    difficulty: Difficulty
    estimated_minutes: int = Field(ge=5, le=180)


class Curriculum(BaseModel):
    model_config = ConfigDict(extra="forbid")

    curriculum_id: str
    canonical_topic: str = Field(min_length=2, max_length=120)
    difficulty: Difficulty
    prerequisites: list[str] = Field(default_factory=list, max_length=8)
    modules: list[CurriculumModule] = Field(min_length=5, max_length=5)
    schema_version: int = 1
    prompt_version: str = "curriculum-v1"

    @model_validator(mode="after")
    def validate_references(self):
        module_ids = [module.module_id for module in self.modules]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("Curriculum module IDs must be unique.")

        concepts = [concept for module in self.modules for concept in module.concepts]
        concept_ids = [concept.concept_id for concept in concepts]
        if len(concept_ids) != len(set(concept_ids)):
            raise ValueError("Curriculum concept IDs must be unique.")
        concept_id_set = set(concept_ids)

        objective_ids = []
        for module in self.modules:
            for concept in module.concepts:
                if not set(concept.prerequisite_ids).issubset(concept_id_set):
                    raise ValueError("A concept references an unknown prerequisite.")
                if concept.concept_id in concept.prerequisite_ids:
                    raise ValueError("A concept cannot be its own prerequisite.")
            for objective in module.learning_objectives:
                objective_ids.append(objective.objective_id)
                if not set(objective.concept_ids).issubset(concept_id_set):
                    raise ValueError("An objective references an unknown concept.")
        if len(objective_ids) != len(set(objective_ids)):
            raise ValueError("Curriculum objective IDs must be unique.")
        return self

    @property
    def subtopics(self) -> list[str]:
        return [module.title for module in self.modules]

    @property
    def concept_ids(self) -> set[str]:
        return {
            concept.concept_id
            for module in self.modules
            for concept in module.concepts
        }

    @property
    def objective_ids(self) -> set[str]:
        return {
            objective.objective_id
            for module in self.modules
            for objective in module.learning_objectives
        }
