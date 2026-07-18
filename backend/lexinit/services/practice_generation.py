from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from backend.clients import get_gemini_model
from backend.lexinit.schemas.curriculum import Curriculum, CurriculumModule
from backend.lexinit.schemas.generated_content import FlashcardSet, MCQSet, OneWordSet, TrueFalseSet
from backend.lexinit.schemas.knowledge import CourseKnowledgePacks, ModuleKnowledgePack
from backend.lexinit.services.curriculum import StructuredGenerator


PRACTICE_PROMPT_VERSION = "practice-v1"


def _stable_id(prefix: str, *parts: object) -> str:
    content = "\x1f".join(str(part).strip().casefold() for part in parts)
    return f"{prefix}_{hashlib.sha256(content.encode('utf-8')).hexdigest()[:20]}"


def _curriculum_context(
    curriculum: Curriculum, knowledge_packs: CourseKnowledgePacks | None = None
) -> str:
    packs_by_module = {
        pack.module_id: pack for pack in (knowledge_packs.packs if knowledge_packs else [])
    }
    payload = {
        "curriculum_id": curriculum.curriculum_id,
        "topic": curriculum.canonical_topic,
        "difficulty": curriculum.difficulty.value,
        "modules": [
            {
                "module_id": module.module_id,
                "title": module.title,
                "concepts": [
                    {"concept_id": concept.concept_id, "name": concept.name}
                    for concept in module.concepts
                ],
                "objectives": [
                    {
                        "objective_id": objective.objective_id,
                        "description": objective.description,
                        "concept_ids": objective.concept_ids,
                    }
                    for objective in module.learning_objectives
                ],
                "common_misconceptions": module.common_misconceptions,
                "knowledge_pack": (
                    packs_by_module[module.module_id].model_dump(mode="json")
                    if module.module_id in packs_by_module
                    else None
                ),
            }
            for module in curriculum.modules
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _references(
    curriculum: Curriculum,
    concept_ids: list[str],
    objective_ids: list[str],
    index: int,
) -> tuple[CurriculumModule, list[str], list[str]]:
    valid_concepts = [item for item in concept_ids if item in curriculum.concept_ids]
    valid_objectives = [item for item in objective_ids if item in curriculum.objective_ids]
    module = curriculum.modules[index % len(curriculum.modules)]
    if valid_concepts:
        module = next(
            (
                candidate
                for candidate in curriculum.modules
                if valid_concepts[0] in {concept.concept_id for concept in candidate.concepts}
            ),
            module,
        )
    elif valid_objectives:
        module = next(
            (
                candidate
                for candidate in curriculum.modules
                if valid_objectives[0]
                in {objective.objective_id for objective in candidate.learning_objectives}
            ),
            module,
        )
    if not valid_concepts:
        valid_concepts = [concept.concept_id for concept in module.concepts]
    if not valid_objectives:
        valid_objectives = [objective.objective_id for objective in module.learning_objectives]
    return module, list(dict.fromkeys(valid_concepts)), list(dict.fromkeys(valid_objectives))


def _lineage(
    curriculum: Curriculum,
    module: CurriculumModule,
    concept_ids: list[str],
    objective_ids: list[str],
    knowledge_pack: ModuleKnowledgePack | None = None,
) -> dict[str, Any]:
    lineage = {
        "curriculum_id": curriculum.curriculum_id,
        "module_id": module.module_id,
        "concept_ids": concept_ids,
        "objective_ids": objective_ids,
        "difficulty": curriculum.difficulty.value,
        "generation_kind": "standard",
        "prompt_version": PRACTICE_PROMPT_VERSION,
        "validation_status": "validated",
    }
    if knowledge_pack:
        lineage["knowledge_pack_id"] = knowledge_pack.knowledge_pack_id
        lineage["knowledge_pack_version"] = knowledge_pack.prompt_version
        lineage["grounding_refs"] = list(knowledge_pack.source_references)
    return lineage


class PracticeGenerator:
    def __init__(self, generator: StructuredGenerator) -> None:
        self._generator = generator

    def _generate_balanced(self, prompt, schema, field_name, curriculum, *, temperature):
        expected_per_module = 10 // len(curriculum.modules)
        repair_instruction = ""
        for _ in range(2):
            result = self._generator.generate_structured(
                prompt + repair_instruction, schema, temperature=temperature
            )
            items = getattr(result, field_name)
            distribution = Counter(
                _references(
                    curriculum, item.concept_ids, item.objective_ids, index
                )[0].module_id
                for index, item in enumerate(items)
            )
            if all(
                distribution[module.module_id] == expected_per_module
                for module in curriculum.modules
            ):
                return result
            repair_instruction = (
                "\n\nREQUIRED CORRECTION: The result must contain exactly two items "
                "for each of the five modules. Reference concepts/objectives from the "
                "matching module so the distribution can be verified."
            )
        raise ValueError("Generated practice was not balanced across all five modules.")

    @staticmethod
    def _pack_for(
        knowledge_packs: CourseKnowledgePacks | None, module: CurriculumModule
    ) -> ModuleKnowledgePack | None:
        return next(
            (pack for pack in (knowledge_packs.packs if knowledge_packs else []) if pack.module_id == module.module_id),
            None,
        )

    def flashcards(self, curriculum: Curriculum, knowledge_packs: CourseKnowledgePacks | None = None) -> list[dict[str, Any]]:
        prompt = (
            "Generate exactly 10 concise study flashcards using the curriculum JSON below. "
            "Generate exactly two flashcards for each of the five modules, use only provided "
            "concept_ids and objective_ids from that module, and avoid duplicates. "
            "Answers must be one word or one short line.\n\n"
            "Every answer must be supported by the matching knowledge_pack.\n\n"
            + _curriculum_context(curriculum, knowledge_packs)
        )
        result = self._generate_balanced(
            prompt, FlashcardSet, "flashcards", curriculum, temperature=0.3
        )
        cards = []
        for index, item in enumerate(result.flashcards):
            module, concept_ids, objective_ids = _references(
                curriculum, item.concept_ids, item.objective_ids, index
            )
            cards.append(
                {
                    "flashcard_id": _stable_id(
                        "flashcard", curriculum.curriculum_id, index, item.question
                    ),
                    "question": item.question.strip(),
                    "answer": item.answer.strip(),
                    **_lineage(curriculum, module, concept_ids, objective_ids, self._pack_for(knowledge_packs, module)),
                }
            )
        return cards

    def mcqs(self, curriculum: Curriculum, knowledge_packs: CourseKnowledgePacks | None = None) -> list[dict[str, Any]]:
        prompt = (
            "Generate exactly 10 multiple-choice questions using the curriculum JSON below. "
            "Each question must have four unique plausible options and one correct_option_index from 0 to 3. "
            "Generate exactly two questions for each of the five modules and use only provided "
            "concept_ids and objective_ids from that module. "
            "For plausible incorrect choices, add misconceptions containing the incorrect option_index and the misconception it indicates. "
            "Never add a misconception for the correct option.\n\n"
            "The answer and explanation must be supported by the matching knowledge_pack.\n\n"
            + _curriculum_context(curriculum, knowledge_packs)
        )
        result = self._generate_balanced(
            prompt, MCQSet, "questions", curriculum, temperature=0.25
        )
        questions = []
        for index, item in enumerate(result.questions):
            module, concept_ids, objective_ids = _references(
                curriculum, item.concept_ids, item.objective_ids, index
            )
            misconception_map = {
                chr(ord("A") + misconception.option_index): misconception.misconception.strip()
                for misconception in item.misconceptions
            }
            questions.append(
                {
                    "question_id": _stable_id("mcq", curriculum.curriculum_id, index, item.question),
                    "question": item.question.strip(),
                    "options": [option.strip() for option in item.options],
                    "answer": item.correct_option_index,
                    "explanation": item.explanation.strip(),
                    "misconception_map": misconception_map,
                    **_lineage(curriculum, module, concept_ids, objective_ids, self._pack_for(knowledge_packs, module)),
                }
            )
        return questions

    def true_false(self, curriculum: Curriculum, knowledge_packs: CourseKnowledgePacks | None = None) -> list[dict[str, Any]]:
        prompt = (
            "Generate exactly 10 unambiguous true/false questions using the curriculum JSON below. "
            "Generate exactly two questions for each of the five modules and use only provided "
            "concept_ids and objective_ids from that module. "
            "Include a concise explanation and misconception_if_wrong when appropriate.\n\n"
            "The answer and explanation must be supported by the matching knowledge_pack.\n\n"
            + _curriculum_context(curriculum, knowledge_packs)
        )
        result = self._generate_balanced(
            prompt, TrueFalseSet, "questions", curriculum, temperature=0.2
        )
        questions = []
        for index, item in enumerate(result.questions):
            module, concept_ids, objective_ids = _references(
                curriculum, item.concept_ids, item.objective_ids, index
            )
            misconception_map = {}
            if item.misconception_if_wrong:
                misconception_map[str(not item.answer).lower()] = item.misconception_if_wrong.strip()
            questions.append(
                {
                    "question_id": _stable_id("truefalse", curriculum.curriculum_id, index, item.question),
                    "question": item.question.strip(),
                    "answer": item.answer,
                    "explanation": item.explanation.strip(),
                    "misconception_map": misconception_map,
                    **_lineage(curriculum, module, concept_ids, objective_ids, self._pack_for(knowledge_packs, module)),
                }
            )
        return questions

    def one_word(self, curriculum: Curriculum, knowledge_packs: CourseKnowledgePacks | None = None) -> list[dict[str, Any]]:
        prompt = (
            "Generate exactly 10 questions whose answers are one word or one hyphenated word, using the curriculum JSON below. "
            "Generate exactly two questions for each of the five modules and use only provided "
            "concept_ids and objective_ids from that module. "
            "Include a concise explanation and misconception_if_wrong when appropriate.\n\n"
            "The answer and explanation must be supported by the matching knowledge_pack.\n\n"
            + _curriculum_context(curriculum, knowledge_packs)
        )
        result = self._generate_balanced(
            prompt, OneWordSet, "questions", curriculum, temperature=0.2
        )
        questions = []
        for index, item in enumerate(result.questions):
            module, concept_ids, objective_ids = _references(
                curriculum, item.concept_ids, item.objective_ids, index
            )
            misconception_map = (
                {"*": item.misconception_if_wrong.strip()}
                if item.misconception_if_wrong
                else {}
            )
            questions.append(
                {
                    "question_id": _stable_id("oneword", curriculum.curriculum_id, index, item.question),
                    "question": item.question.strip(),
                    "answer": item.answer.strip(),
                    "explanation": item.explanation.strip(),
                    "misconception_map": misconception_map,
                    **_lineage(curriculum, module, concept_ids, objective_ids, self._pack_for(knowledge_packs, module)),
                }
            )
        return questions


def practice_generator(model_name: str | None = None) -> PracticeGenerator:
    return PracticeGenerator(get_gemini_model(model_name))
