"""Guards against bad AI-written questions.

* ``verify_answer_keys`` asks the model to solve freshly written questions
  without seeing the answer key, and rejects any whose key it disagrees with.
  A wrong key marks a learner wrong for a right answer and corrupts their
  mastery, so a disputed question is dropped rather than shown.
* ``report_question`` records a learner's report and takes the question out
  of their future attempts.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from backend.lexinit.api.errors import ApiError
from backend.lexinit.domain.assessment.grading import text_answer_matches
from backend.lexinit.services.curriculum import StructuredGenerator


logger = logging.getLogger(__name__)

REPORT_REASONS = {"wrong_answer", "unclear", "off_topic", "other"}


class SolvedQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0, le=60)
    answer: str = Field(min_length=1, max_length=120)
    ambiguous: bool = False
    # Other equally correct one-word answers (synonyms, abbreviations).
    alternatives: list[str] = Field(default_factory=list, max_length=4)


class SolvedSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answers: list[SolvedQuestion] = Field(max_length=60)


def _question_type(question: dict[str, Any]) -> str:
    if question.get("type"):
        return str(question["type"])
    if isinstance(question.get("options"), list) and question["options"]:
        return "mcq"
    return "truefalse" if isinstance(question.get("answer"), bool) else "oneword"


def _key_matches(question: dict[str, Any], solved: str) -> bool:
    kind = _question_type(question)
    value = solved.strip()
    key = question.get("answer")
    if kind == "mcq":
        options = question.get("options") or []
        if not isinstance(key, int) or not 0 <= key < len(options):
            return False
        letter = chr(ord("A") + key)
        return value[:1].upper() == letter or value.casefold() == str(options[key]).strip().casefold()
    if kind == "truefalse":
        return value.casefold() in {"true", "false"} and (value.casefold() == "true") is bool(key)
    return text_answer_matches(value, [str(key)])


def verify_answer_keys(
    generator: StructuredGenerator, questions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return only the questions whose answer key an independent solve agrees
    with. If the check itself fails, the questions are returned unchanged."""
    if not questions:
        return questions
    payload = []
    for index, question in enumerate(questions):
        kind = _question_type(question)
        item: dict[str, Any] = {"index": index, "type": kind, "question": question.get("question")}
        if kind == "mcq":
            item["options"] = {
                chr(ord("A") + position): option
                for position, option in enumerate(question.get("options") or [])
            }
        elif kind == "oneword":
            # Free recall has synonyms, so the solver judges the proposed
            # answer instead of having to guess the exact same word.
            item["proposed_answer"] = question.get("answer")
        payload.append(item)
    prompt = (
        "Solve each question independently and carefully. For multiple-choice questions answer "
        "with the option letter. For true/false answer 'true' or 'false'. For one-word questions "
        "a proposed_answer is given: answer with the single word you consider correct (repeat "
        "the proposed answer only if it is correct), and list any other equally correct "
        "one-word answers in alternatives. Set ambiguous to true when a question has no single clearly "
        "correct answer, has two defensible options, or cannot be answered as written.\n\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    try:
        solved = generator.generate_structured(prompt, SolvedSet, temperature=0.0)
    except Exception:
        logger.warning("answer_key_verification_unavailable", exc_info=True)
        return questions
    by_index = {item.index: item for item in solved.answers}
    kept = []
    for index, question in enumerate(questions):
        answer = by_index.get(index)
        if answer is None:
            kept.append(question)  # not checked; do not punish the question
            continue
        agrees = _key_matches(question, answer.answer)
        if not agrees and _question_type(question) == "oneword":
            agrees = text_answer_matches(str(question.get("answer")), answer.alternatives)
        if answer.ambiguous or not agrees:
            logger.info("answer_key_rejected question=%r", str(question.get("question"))[:120])
            continue
        if _question_type(question) == "oneword":
            accepted = [
                value.strip()
                for value in [answer.answer, *answer.alternatives]
                if value.strip() and not text_answer_matches(value, [str(question.get("answer"))])
            ]
            if accepted:
                question = {**question, "accepted_answers": accepted[:4]}
        kept.append(question)
    return kept


def report_question(
    db,
    *,
    user_id: ObjectId,
    source: str,
    reference_id: str,
    question_index: int,
    reason: str,
    note: str,
) -> dict[str, Any]:
    """Record a learner's report of a faulty question."""
    if reason not in REPORT_REASONS:
        raise ApiError("Choose a reason for the report.", code="invalid_report_reason")
    question_text = ""
    bank_question_id = None
    session_id = None
    if source == "assessment":
        try:
            submission = db.assessment_submissions.find_one(
                {"_id": ObjectId(reference_id), "user_id": user_id}
            )
        except Exception:
            submission = None
        if not submission or not 0 <= question_index < len(submission.get("questions") or []):
            raise ApiError("Question not found.", status_code=404, code="question_not_found")
        question_text = str(submission["questions"][question_index].get("question") or "")
        refs = submission.get("question_refs") or []
        if question_index < len(refs):
            bank_question_id = refs[question_index].get("bank_question_id")
        session_id = submission.get("session_id")
    elif source == "final":
        final = db.final_assessments.find_one({"_id": reference_id, "user_id": user_id})
        if not final or not 0 <= question_index < len(final.get("questions") or []):
            raise ApiError("Question not found.", status_code=404, code="question_not_found")
        question_text = str(final["questions"][question_index].get("question") or "")
        session_id = final.get("session_id")
    elif source == "check":
        check = db.coach_checks.find_one({"_id": reference_id, "user_id": user_id})
        if not check:
            raise ApiError("Question not found.", status_code=404, code="question_not_found")
        question_text = str(check.get("question") or "")
        session_id = check.get("session_id")
    else:
        raise ApiError("Unknown question source.", code="invalid_report_source")

    report_id = f"{source}:{reference_id}:{question_index}"
    db.question_reports.update_one(
        {"_id": report_id, "user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "source": source,
                "reference_id": reference_id,
                "question_index": question_index,
                "session_id": session_id,
                "question": question_text[:600],
                "reason": reason,
                "note": note.strip()[:500],
                "status": "open",
                "updated_at": datetime.datetime.now(datetime.timezone.utc),
            },
            "$setOnInsert": {"created_at": datetime.datetime.now(datetime.timezone.utc)},
        },
        upsert=True,
    )
    if bank_question_id:
        # Do not ask this learner the reported question again.
        db.assessment_question_bank.update_one(
            {"_id": bank_question_id, "user_id": user_id}, {"$set": {"reported": True}}
        )
    return {"report_id": report_id, "status": "open"}
