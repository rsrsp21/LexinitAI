"""Builders shared by tests."""

from __future__ import annotations

import datetime
import uuid

MODULE_COUNT = 5


def build_course(user_id, *, topic="Test Course"):
    """A complete synthetic course: five modules, two concepts each, and two
    questions of each type per module."""
    from bson import ObjectId

    tag = uuid.uuid4().hex[:8]
    modules, materials, packs = [], [], []
    questions = {"mcqs": [], "true_false": [], "oneword": [], "flashcards": []}
    for index in range(MODULE_COUNT):
        module_id = f"module_{tag}_{index}"
        concept_ids = [f"concept_{tag}_{index}_{position}" for position in range(2)]
        objective_id = f"objective_{tag}_{index}"
        modules.append(
            {
                "module_id": module_id,
                "title": f"Module {index + 1}",
                "concepts": [
                    {
                        "concept_id": concept_id,
                        "name": f"Concept {index + 1}.{position + 1}",
                        "prerequisite_ids": [],
                        "difficulty": "easy",
                    }
                    for position, concept_id in enumerate(concept_ids)
                ],
                "learning_objectives": [
                    {
                        "objective_id": objective_id,
                        "description": f"Explain the ideas of module {index + 1}.",
                        "concept_ids": concept_ids[:1],
                    }
                ],
                "common_misconceptions": [],
                "difficulty": "easy",
                "estimated_minutes": 30,
            }
        )
        lineage = {
            "module_id": module_id,
            "concept_ids": concept_ids[:1],
            "objective_ids": [objective_id],
            "difficulty": "easy",
        }
        materials.append({"subtopic": f"Module {index + 1}", "study_material": "Study text. " * 60, **lineage})
        packs.append(
            {
                "module_id": module_id,
                "definitions": [{"term": "Term", "definition": "A definition."}],
                "important_facts": ["Fact one.", "Fact two."],
            }
        )
        for position in range(2):
            label = f"{index + 1}.{position + 1}"
            questions["mcqs"].append(
                {
                    "question_id": f"mcq_{tag}_{index}_{position}",
                    "question": f"Choice question {label}?",
                    "options": ["first", "second", "third", "fourth"],
                    "answer": 1,
                    "explanation": "The second option is correct.",
                    "misconception_map": {"A": "Picks the first option by habit."},
                    **lineage,
                }
            )
            questions["true_false"].append(
                {
                    "question_id": f"tf_{tag}_{index}_{position}",
                    "question": f"Statement {label} is true.",
                    "answer": True,
                    "explanation": "It is true.",
                    "misconception_map": {},
                    **lineage,
                }
            )
            questions["oneword"].append(
                {
                    "question_id": f"word_{tag}_{index}_{position}",
                    "question": f"Name the term for {label}.",
                    "answer": "photosynthesis",
                    "explanation": "The term is photosynthesis.",
                    "misconception_map": {},
                    **lineage,
                }
            )
            questions["flashcards"].append(
                {"flashcard_id": f"card_{tag}_{index}_{position}", "question": f"Card {label}?", "answer": "answer", **lineage}
            )
    return {
        "_id": ObjectId(),
        "generation_run_id": uuid.uuid4().hex,
        "user_id": user_id,
        "topic": topic,
        "normalized_topic": topic.casefold(),
        "difficulty_level": "easy",
        "generation_mode": "Basic",
        "curriculum_id": f"curriculum_{tag}",
        "curriculum": {"curriculum_id": f"curriculum_{tag}", "modules": modules},
        "module_knowledge_packs": packs,
        "study_materials": materials,
        "course_content": [],
        "learningpath": "",
        "additionalresources": [],
        "created_at": datetime.datetime.now(datetime.timezone.utc),
        **questions,
    }
