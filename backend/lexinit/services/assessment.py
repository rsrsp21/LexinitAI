from __future__ import annotations

import datetime
from collections.abc import Callable
from typing import Any

from bson import ObjectId

from backend.lexinit.domain.assessment import grade_assessment, questions_for_assessment
from backend.lexinit.repositories.assessments import AssessmentSubmissionRepository
from backend.lexinit.schemas.assessment import AssessmentSubmissionOutcome, AssessmentType
from backend.lexinit.schemas.adaptive import AdaptiveUpdateResult
from backend.lexinit.services.adaptive import AdaptiveLearningService


SCORE_FIELDS: dict[AssessmentType, str] = {
    AssessmentType.MCQ: "mcq_scores",
    AssessmentType.TRUE_FALSE: "truefalse_scores",
    AssessmentType.ONE_WORD: "oneword_scores",
}


class AssessmentSubmissionService:
    def __init__(
        self,
        repository: AssessmentSubmissionRepository,
        weak_topic_analyzer: Callable[[str], str],
        adaptive_learning_service: AdaptiveLearningService | None = None,
    ) -> None:
        self._repository = repository
        self._weak_topic_analyzer = weak_topic_analyzer
        self._adaptive_learning_service = adaptive_learning_service

    def submit(
        self,
        *,
        user_id: ObjectId,
        requested_session_id: str,
        session_data: dict[str, Any],
        assessment_type: AssessmentType,
        answers: list[Any],
        questions_override: list[dict[str, Any]] | None = None,
        attempt_id: str | None = None,
    ) -> AssessmentSubmissionOutcome:
        questions = questions_override or questions_for_assessment(session_data, assessment_type)
        grading = grade_assessment(assessment_type, questions, answers)

        weak_topic = ""
        adaptive_error = ""
        if grading.incorrect_context:
            try:
                weak_topic = self._weak_topic_analyzer(grading.incorrect_context).strip()
            except Exception:
                adaptive_error = "Weak-topic analysis is temporarily unavailable."

        now = datetime.datetime.now(datetime.timezone.utc)
        submission_id = ObjectId()
        source_session_id = session_data.get("_id", requested_session_id)
        source_topic = str(session_data.get("topic") or "Untitled course")
        feedback = [item.model_dump(mode="python") for item in grading.feedback]
        question_snapshots = [
            item.model_dump(mode="python", exclude_none=True) for item in grading.question_snapshots
        ]
        module_ids = {
            str(question.get("module_id"))
            for question in questions
            if question.get("module_id")
        }
        submission = {
            "_id": submission_id,
            "user_id": user_id,
            "session_id": source_session_id,
            "source_topic": source_topic,
            "assessment_type": assessment_type.value,
            "score_field": SCORE_FIELDS[assessment_type],
            "score": grading.score,
            "total": grading.total,
            "selected_answers": list(answers),
            "questions": question_snapshots,
            "feedback": feedback,
            "weak_topic": weak_topic,
            "created_at": now,
            "grading_version": 1,
            "attempt_id": attempt_id,
            "module_id": next(iter(module_ids)) if len(module_ids) == 1 else None,
        }
        self._repository.insert(submission)

        adaptive_result = AdaptiveUpdateResult()
        if self._adaptive_learning_service is not None:
            try:
                adaptive_result = self._adaptive_learning_service.record_assessment(
                    user_id=str(user_id),
                    submission_id=str(submission_id),
                    requested_session_id=requested_session_id,
                    session_data=session_data,
                    assessment_type=assessment_type,
                    questions=questions,
                    grading=grading,
                    observed_at=now,
                )
                self._repository.set_adaptive_result(
                    submission_id,
                    {
                        "status": "completed",
                        "mastery_updates": [
                            item.model_dump(mode="python") for item in adaptive_result.mastery_updates
                        ],
                        "decisions": [
                            item.model_dump(mode="python") for item in adaptive_result.decisions
                        ],
                    },
                )
            except Exception:
                mastery_error = "Mastery update is temporarily unavailable."
                adaptive_error = f"{adaptive_error} {mastery_error}".strip()
                try:
                    self._repository.set_adaptive_result(
                        submission_id,
                        {"status": "failed", "retryable": True},
                    )
                except Exception:
                    pass

        return AssessmentSubmissionOutcome(
            submission_id=str(submission_id),
            source_session_id=str(source_session_id),
            source_topic=source_topic,
            score=grading.score,
            total=grading.total,
            feedback=grading.feedback,
            adaptive_topic=weak_topic,
            adaptive_error=adaptive_error,
            mastery_updates=adaptive_result.mastery_updates,
            adaptation_decisions=adaptive_result.decisions,
            attempt_id=attempt_id,
        )
