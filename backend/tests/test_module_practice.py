"""Per-module practice: shape, grounding prompt, and answer-key handling."""

import pytest

from backend.lexinit.schemas.curriculum import Curriculum
from backend.lexinit.schemas.generated_content import (
    FlashcardDraft,
    MCQDraft,
    OneWordDraft,
    TrueFalseDraft,
)
from backend.lexinit.schemas.knowledge import ModuleKnowledgePack
from backend.lexinit.services.practice_generation import (
    ITEMS_PER_MODULE,
    ModulePracticeDraft,
    generate_module_practice,
)


def make_curriculum() -> Curriculum:
    modules = []
    for index in range(5):
        modules.append(
            {
                "module_id": f"module_{index}",
                "title": f"Module {index}",
                "concepts": [
                    {
                        "concept_id": f"concept_{index}_{position}",
                        "name": f"Concept {index}-{position}",
                        "difficulty": "easy",
                    }
                    for position in range(2)
                ],
                "learning_objectives": [
                    {
                        "objective_id": f"objective_{index}",
                        "description": f"Explain the ideas of module {index}.",
                        "concept_ids": [f"concept_{index}_0"],
                    }
                ],
                "difficulty": "easy",
                "estimated_minutes": 30,
            }
        )
    return Curriculum(
        curriculum_id="curriculum_1",
        canonical_topic="Test topic",
        difficulty="easy",
        modules=modules,
    )


def make_pack(module_id: str) -> ModuleKnowledgePack:
    return ModuleKnowledgePack(
        knowledge_pack_id=f"pack_{module_id}",
        curriculum_id="curriculum_1",
        module_id=module_id,
        module_title="Module",
        difficulty="easy",
        concept_ids=["concept_0_0"],
        objective_ids=["objective_0"],
        required_concepts=["Concept"],
        important_facts=["Fact one.", "Fact two."],
        video_search_terms=["term one", "term two"],
    )


def make_draft(tag: str, concept_ids=None) -> ModulePracticeDraft:
    concept_ids = concept_ids or []
    return ModulePracticeDraft(
        flashcards=[
            FlashcardDraft(question=f"Card {tag} {i}?", answer="answer", concept_ids=concept_ids)
            for i in range(2)
        ],
        mcqs=[
            MCQDraft(
                question=f"Choice {tag} {i}?",
                options=["a", "b", "c", "d"],
                correct_option_index=1,
                explanation="Because b.",
                misconceptions=[{"option_index": 0, "misconception": "Confuses a with b."}],
                concept_ids=concept_ids,
            )
            for i in range(3)
        ],
        true_false=[
            TrueFalseDraft(question=f"Statement {tag} {i}.", answer=True, explanation="It is true.")
            for i in range(3)
        ],
        one_word=[
            OneWordDraft(question=f"Word {tag} {i}?", answer="term", explanation="The term.")
            for i in range(3)
        ],
    )


class FakeGenerator:
    def __init__(self, drafts):
        self.drafts = list(drafts)
        self.prompts = []

    def generate_structured(self, prompt, schema, *, temperature=0.2):
        self.prompts.append(prompt)
        return self.drafts.pop(0)


def run(generator, verify=None, material="The study text explains everything."):
    curriculum = make_curriculum()
    module = curriculum.modules[2]
    return generate_module_practice(
        generator, curriculum, module, make_pack(module.module_id), material, verify=verify
    )


def test_two_items_of_each_kind_with_module_lineage():
    result = run(FakeGenerator([make_draft("a")]))
    assert {field: len(items) for field, items in result.items()} == {
        "flashcards": ITEMS_PER_MODULE,
        "mcqs": ITEMS_PER_MODULE,
        "true_false": ITEMS_PER_MODULE,
        "oneword": ITEMS_PER_MODULE,
    }
    for items in result.values():
        for item in items:
            assert item["module_id"] == "module_2"
            assert item["knowledge_pack_id"] == "pack_module_2"
            assert item["grounded_in"] == "study_material"
            assert set(item["concept_ids"]) <= {"concept_2_0", "concept_2_1"}
            assert item["objective_ids"] == ["objective_2"]
    mcq = result["mcqs"][0]
    assert mcq["answer"] == 1 and mcq["misconception_map"] == {"A": "Confuses a with b."}
    assert result["true_false"][0]["misconception_map"] == {}
    assert len({item["question_id"] for item in result["mcqs"]}) == ITEMS_PER_MODULE


def test_concepts_from_other_modules_are_replaced_by_this_module():
    result = run(FakeGenerator([make_draft("a", concept_ids=["concept_0_0", "concept_2_1"])]))
    assert result["mcqs"][0]["concept_ids"] == ["concept_2_1"]
    wrong_only = run(FakeGenerator([make_draft("b", concept_ids=["concept_4_0"])]))
    assert wrong_only["mcqs"][0]["concept_ids"] == ["concept_2_0", "concept_2_1"]


def test_the_study_material_is_in_the_prompt_before_the_task():
    generator = FakeGenerator([make_draft("a")])
    run(generator, material="UNIQUE STUDY TEXT ABOUT GRADIENTS")
    prompt = generator.prompts[0]
    assert "UNIQUE STUDY TEXT ABOUT GRADIENTS" in prompt
    assert prompt.index("UNIQUE STUDY TEXT") < prompt.index("TASK:")
    assert "Module 2" in prompt and "Module 3" not in prompt  # only this module is sent


def test_one_generation_call_when_enough_questions_are_verified():
    generator = FakeGenerator([make_draft("a")])
    calls = []

    def verify(questions):
        calls.append(len(questions))
        return [item for item in questions if not item["question"].endswith(" 0?") and not item["question"].endswith(" 0.")]

    result = run(generator, verify=verify)
    assert len(generator.prompts) == 1
    assert calls == [9]  # one check covering all three question types
    assert [item["question"] for item in result["mcqs"]] == ["Choice a 1?", "Choice a 2?"]
    assert all(item["validation_status"] == "validated" for item in result["mcqs"])


def test_a_second_set_is_written_when_too_few_are_verified():
    generator = FakeGenerator([make_draft("a"), make_draft("b")])

    def verify(questions):
        return [item for item in questions if " b " in item["question"]]

    result = run(generator, verify=verify)
    assert len(generator.prompts) == 2
    assert "REQUIRED CORRECTION" in generator.prompts[1]
    assert all(" b " in item["question"] for item in result["mcqs"] + result["true_false"] + result["oneword"])
    assert all(item["validation_status"] == "validated" for item in result["oneword"])


def test_unverified_questions_fill_the_gap_and_are_marked():
    generator = FakeGenerator([make_draft("a"), make_draft("b")])
    result = run(generator, verify=lambda questions: [])
    for field in ("mcqs", "true_false", "oneword"):
        assert len(result[field]) == ITEMS_PER_MODULE
        assert all(item["validation_status"] == "unverified" for item in result[field])


def test_enriched_questions_from_the_check_are_kept():
    generator = FakeGenerator([make_draft("a")])

    def verify(questions):
        return [
            {**item, "accepted_answers": ["synonym"]} if "Word" in item["question"] else item
            for item in questions
        ]

    result = run(generator, verify=verify)
    assert result["oneword"][0]["accepted_answers"] == ["synonym"]


def test_duplicate_questions_within_a_module_are_not_kept_twice():
    draft = make_draft("a")
    draft.mcqs[1] = draft.mcqs[0].model_copy()
    result = run(FakeGenerator([draft]))
    assert len({item["question"] for item in result["mcqs"]}) == ITEMS_PER_MODULE


def test_an_incomplete_module_is_an_error_not_a_short_course():
    draft = make_draft("a")
    draft.mcqs[1] = draft.mcqs[0].model_copy()
    draft.mcqs[2] = draft.mcqs[0].model_copy()
    second = make_draft("a")
    second.mcqs[1] = second.mcqs[0].model_copy()
    second.mcqs[2] = second.mcqs[0].model_copy()
    with pytest.raises(ValueError, match="incomplete"):
        run(FakeGenerator([draft, second]))
