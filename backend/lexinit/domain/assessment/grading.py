from __future__ import annotations

import re
import unicodedata
from typing import Any

from backend.lexinit.schemas.assessment import (
    AssessmentType,
    GradingResult,
    QuestionFeedback,
    QuestionSnapshot,
)


ASSESSMENT_FIELDS: dict[AssessmentType, tuple[str, ...]] = {
    AssessmentType.MCQ: ("mcqs", "mcq", "mcq_questions"),
    AssessmentType.TRUE_FALSE: ("true_false", "truefalse", "true_false_questions"),
    AssessmentType.ONE_WORD: ("oneword", "one_word", "oneword_questions", "one_word_questions"),
}


class AssessmentSubmissionError(ValueError):
    """The learner submission is incomplete or contains invalid answer data."""


class AssessmentIntegrityError(RuntimeError):
    """Stored assessment content is malformed and cannot be graded safely."""


def questions_for_assessment(session_data: dict[str, Any], assessment_type: AssessmentType) -> list[dict[str, Any]]:
    for field in ASSESSMENT_FIELDS[assessment_type]:
        value = session_data.get(field)
        if isinstance(value, list):
            if not value:
                break
            if not all(isinstance(question, dict) for question in value):
                raise AssessmentIntegrityError("The stored assessment contains an invalid question.")
            return value
    raise AssessmentSubmissionError("This assessment has no questions.")


def _normalize_mcq_answer(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text.isdigit():
        return int(text)
    if len(text) == 1 and "a" <= text <= "z":
        return ord(text) - ord("a")
    return -1


def _normalize_stored_boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return None


_LEADING_ARTICLE_RE = re.compile(r"^(?:a|an|the)\s+")
_NON_WORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
# Longer answers tolerate one or two typos; short ones must match exactly,
# because a single changed letter there is usually a different word.
FUZZY_MIN_LENGTH = 5
FUZZY_TWO_TYPO_LENGTH = 10
ACCEPTED_ANSWER_FIELDS = ("accepted_answers", "alternative_answers", "aliases")


def _normalize_text_answer(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
    text = text.replace("-", " ").replace("_", " ")
    text = _NON_WORD_RE.sub("", text)
    text = " ".join(text.split())
    return _LEADING_ARTICLE_RE.sub("", text)


def _accepted_text_answers(question: dict[str, Any], correct_answer: str) -> list[str]:
    accepted = [correct_answer]
    for field in ACCEPTED_ANSWER_FIELDS:
        values = question.get(field)
        if isinstance(values, list):
            accepted.extend(str(item) for item in values[:12] if str(item or "").strip())
    return accepted


def _edit_distance(left: str, right: str, limit: int) -> int:
    """Levenshtein distance, returning limit + 1 as soon as it is exceeded."""
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous = list(range(len(right) + 1))
    for row, left_char in enumerate(left, start=1):
        current = [row]
        for column, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (left_char != right_char),
                )
            )
        if min(current) > limit:
            return limit + 1
        previous = current
    return previous[-1]


def text_answer_matches(submitted: Any, accepted_answers: list[str]) -> bool:
    """True when a typed answer matches any accepted answer, allowing for
    case, punctuation, a leading article, and small typos in longer words."""
    answer = _normalize_text_answer(submitted)
    if not answer:
        return False
    for candidate in accepted_answers:
        expected = _normalize_text_answer(candidate)
        if not expected:
            continue
        if answer == expected or answer.replace(" ", "") == expected.replace(" ", ""):
            return True
        if any(character.isdigit() for character in expected + answer):
            continue  # numbers, dates and formulas must be exact
        if min(len(answer), len(expected)) < FUZZY_MIN_LENGTH:
            continue
        # One typo in a medium word, two in a long one. Tighter than a
        # similarity ratio, which would accept "mitosis" for "meiosis".
        allowed = 2 if min(len(answer), len(expected)) >= FUZZY_TWO_TYPO_LENGTH else 1
        if answer[0] == expected[0] and _edit_distance(answer, expected, allowed) <= allowed:
            return True
    return False


def _question_text(question: dict[str, Any], index: int) -> str:
    text = str(question.get("question") or question.get("q") or "").strip()
    if not text:
        raise AssessmentIntegrityError(f"Stored question {index + 1} has no question text.")
    return text


def _mcq_options(question: dict[str, Any], index: int) -> list[str]:
    options = question.get("options")
    if not isinstance(options, list) or len(options) < 2 or len(options) > 10:
        raise AssessmentIntegrityError(f"Stored question {index + 1} has invalid options.")
    if any(not isinstance(option, str) or not option.strip() or len(option) > 500 for option in options):
        raise AssessmentIntegrityError(f"Stored question {index + 1} has invalid options.")
    if len({option.strip().casefold() for option in options}) != len(options):
        raise AssessmentIntegrityError(f"Stored question {index + 1} has duplicate options.")
    return options


def _validate_submitted_answers(
    assessment_type: AssessmentType,
    questions: list[dict[str, Any]],
    answers: list[Any],
) -> None:
    if len(answers) != len(questions):
        raise AssessmentSubmissionError("Answer every question before submitting.")

    for index, answer in enumerate(answers):
        if assessment_type is AssessmentType.MCQ:
            options = _mcq_options(questions[index], index)
            if isinstance(answer, bool) or not isinstance(answer, int) or not 0 <= answer < len(options):
                raise AssessmentSubmissionError(f"Invalid answer for question {index + 1}.")
        elif assessment_type is AssessmentType.TRUE_FALSE:
            if not isinstance(answer, bool):
                raise AssessmentSubmissionError(f"Invalid answer for question {index + 1}.")
        elif not isinstance(answer, str) or not answer.strip() or len(answer.strip()) > 200:
            raise AssessmentSubmissionError(f"Invalid answer for question {index + 1}.")


def grade_assessment(
    assessment_type: AssessmentType,
    questions: list[dict[str, Any]],
    answers: list[Any],
) -> GradingResult:
    if not questions:
        raise AssessmentSubmissionError("This assessment has no questions.")
    _validate_submitted_answers(assessment_type, questions, answers)

    score = 0
    feedback: list[QuestionFeedback] = []
    snapshots: list[QuestionSnapshot] = []
    incorrect_explanations: list[str] = []

    for index, question in enumerate(questions):
        question_text = _question_text(question, index)
        stored_answer = question.get("answer", question.get("correct_answer"))
        submitted_answer = answers[index]
        options: list[str] | None = None
        selected_option: str | None = None

        if assessment_type is AssessmentType.MCQ:
            options = _mcq_options(question, index)
            correct_answer: Any = _normalize_mcq_answer(stored_answer)
            if not 0 <= correct_answer < len(options):
                raise AssessmentIntegrityError(f"Stored question {index + 1} has an invalid correct answer.")
            is_correct = submitted_answer == correct_answer
            selected_option = options[submitted_answer]
        elif assessment_type is AssessmentType.TRUE_FALSE:
            correct_answer = _normalize_stored_boolean(stored_answer)
            if correct_answer is None:
                raise AssessmentIntegrityError(f"Stored question {index + 1} has an invalid correct answer.")
            is_correct = submitted_answer is correct_answer
        else:
            correct_answer = str(stored_answer or "").strip()
            if not correct_answer or len(correct_answer) > 200:
                raise AssessmentIntegrityError(f"Stored question {index + 1} has an invalid correct answer.")
            is_correct = text_answer_matches(
                submitted_answer, _accepted_text_answers(question, correct_answer)
            )

        explanation = str(question.get("explanation") or "").strip()
        if is_correct:
            score += 1
        else:
            detail = explanation or f"The correct answer is {correct_answer}."
            incorrect_explanations.append(
                f"{index + 1}. {question_text}\nCorrect-answer explanation: {detail}"
            )

        feedback.append(
            QuestionFeedback(
                correct=is_correct,
                correct_answer=correct_answer,
                explanation=explanation,
            )
        )
        snapshots.append(
            QuestionSnapshot(
                question=question_text,
                selected_answer=submitted_answer,
                options=options,
                selected_option=selected_option,
            )
        )

    return GradingResult(
        score=score,
        total=len(questions),
        feedback=feedback,
        question_snapshots=snapshots,
        incorrect_context="\n\n".join(incorrect_explanations),
    )
