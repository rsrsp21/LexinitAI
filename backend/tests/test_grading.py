import pytest

from backend.lexinit.domain.assessment import AssessmentSubmissionError, grade_assessment
from backend.lexinit.domain.assessment.grading import text_answer_matches
from backend.lexinit.schemas.assessment import AssessmentType


@pytest.mark.parametrize(
    ("submitted", "accepted", "expected"),
    [
        ("Photosynthesys", ["photosynthesis"], True),  # one typo in a long word
        ("the mitochondria", ["Mitochondria"], True),  # leading article
        ("q-learning", ["Q learning"], True),  # hyphen and case
        ("Bellman eqution", ["Bellman equation"], True),
        ("DNA", ["deoxyribonucleic acid", "DNA"], True),  # accepted alternative
        ("DNA", ["deoxyribonucleic acid"], False),
        ("mitosis", ["meiosis"], False),  # close but a different word
        ("increase", ["decrease"], False),
        ("cat", ["car"], False),  # short words must match exactly
        ("1945", ["1946"], False),  # numbers must match exactly
        ("", ["anything"], False),
    ],
)
def test_text_answer_matching(submitted, accepted, expected):
    assert text_answer_matches(submitted, accepted) is expected


def test_one_word_grading_uses_accepted_answers():
    question = {
        "question": "What molecule carries genetic information?",
        "answer": "deoxyribonucleic-acid",
        "accepted_answers": ["DNA"],
        "explanation": "DNA stores genetic information.",
    }
    result = grade_assessment(AssessmentType.ONE_WORD, [question], ["dna"])
    assert result.score == 1


def test_multiple_choice_grading_and_snapshot():
    question = {
        "question": "What is 2 + 2?",
        "options": ["3", "4", "5", "6"],
        "answer": 1,
        "explanation": "2 + 2 = 4.",
    }
    right = grade_assessment(AssessmentType.MCQ, [question], [1])
    wrong = grade_assessment(AssessmentType.MCQ, [question], [0])
    assert (right.score, wrong.score) == (1, 0)
    assert wrong.question_snapshots[0].selected_option == "3"
    assert wrong.feedback[0].correct_answer == 1


def test_true_false_rejects_non_boolean_answers():
    question = {"question": "The sky is green.", "answer": False, "explanation": "It is blue."}
    with pytest.raises(AssessmentSubmissionError):
        grade_assessment(AssessmentType.TRUE_FALSE, [question], ["false"])


def test_every_question_needs_an_answer():
    question = {"question": "The sky is green.", "answer": False, "explanation": "It is blue."}
    with pytest.raises(AssessmentSubmissionError):
        grade_assessment(AssessmentType.TRUE_FALSE, [question, question], [False])
