from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from backend.lexinit.domain.mastery import calculate_mastery, choose_adaptation
from backend.lexinit.repositories.adaptive import AdaptiveLearningRepository
from backend.lexinit.schemas.adaptive import AdaptiveUpdateResult, MasteryEvidence
from backend.lexinit.schemas.assessment import AssessmentType, GradingResult
from backend.lexinit.schemas.generation import Difficulty


SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _stable_id(prefix: str, *parts: object) -> str:
    content = "\x1f".join(str(part) for part in parts)
    return f"{prefix}_{hashlib.sha256(content.encode('utf-8')).hexdigest()[:24]}"


def legacy_topic_concept_id(topic: str) -> str:
    normalized = " ".join(topic.strip().casefold().split()) or "untitled"
    return _stable_id("legacy_topic", normalized)


def _safe_id_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str) and SAFE_ID_RE.fullmatch(item.strip()) and item.strip() not in result:
            result.append(item.strip())
    return result


def _difficulty(value: Any) -> Difficulty:
    try:
        value = getattr(value, "value", value)
        return Difficulty(str(value or "medium").strip().lower())
    except ValueError:
        return Difficulty.MEDIUM


def _question_id(question: dict[str, Any], session_id: str, index: int) -> str:
    candidate = question.get("question_id") or question.get("id")
    if isinstance(candidate, str) and SAFE_ID_RE.fullmatch(candidate.strip()):
        return candidate.strip()
    question_text = question.get("question") or question.get("q") or f"question-{index + 1}"
    return _stable_id("legacy_question", session_id, index, question_text)


def _concept_label(question: dict[str, Any], concept_id: str, source_topic: str) -> str:
    labels = question.get("concept_labels")
    if isinstance(labels, dict) and isinstance(labels.get(concept_id), str):
        return labels[concept_id].strip()[:200] or concept_id
    label = question.get("concept_name") or question.get("concept")
    if isinstance(label, str) and label.strip():
        return label.strip()[:200]
    return source_topic[:200]


def _misconception(
    question: dict[str, Any],
    assessment_type: AssessmentType,
    selected_answer: Any,
    selected_option: str | None,
) -> tuple[str | None, str | None]:
    mapping = question.get("misconception_map")
    if not isinstance(mapping, dict):
        return None, None

    candidates = [str(selected_answer)]
    if assessment_type is AssessmentType.MCQ and isinstance(selected_answer, int):
        candidates.extend([chr(ord("A") + selected_answer), chr(ord("a") + selected_answer)])
    if selected_option:
        candidates.append(selected_option)

    folded_mapping = {str(key).strip().casefold(): value for key, value in mapping.items()}
    raw = next(
        (folded_mapping[candidate.strip().casefold()] for candidate in candidates if candidate.strip().casefold() in folded_mapping),
        None,
    )
    if raw is None:
        raw = folded_mapping.get("*")
    if not isinstance(raw, str) or not raw.strip():
        return None, None
    label = raw.strip()[:300]
    identifier = label if SAFE_ID_RE.fullmatch(label) else _stable_id("misconception", label.casefold())
    return identifier, label


class AdaptiveLearningService:
    def __init__(self, repository: AdaptiveLearningRepository) -> None:
        self._repository = repository

    def record_assessment(
        self,
        *,
        user_id: str,
        submission_id: str,
        requested_session_id: str,
        session_data: dict[str, Any],
        assessment_type: AssessmentType,
        questions: list[dict[str, Any]],
        grading: GradingResult,
        observed_at: datetime,
    ) -> AdaptiveUpdateResult:
        source_topic = str(session_data.get("topic") or "Untitled course").strip()
        session_id = str(session_data.get("_id", requested_session_id))
        fallback_concept_id = legacy_topic_concept_id(source_topic)
        result = AdaptiveUpdateResult()

        for index, (question, feedback, snapshot) in enumerate(
            zip(questions, grading.feedback, grading.question_snapshots, strict=True)
        ):
            concept_ids = _safe_id_list(question.get("concept_ids")) or [fallback_concept_id]
            prerequisite_ids = _safe_id_list(question.get("prerequisite_concept_ids"))
            objective_ids = _safe_id_list(question.get("objective_ids"))
            difficulty = _difficulty(question.get("difficulty") or session_data.get("difficulty_level"))
            misconception_id, misconception_label = (None, None)
            if not feedback.correct:
                misconception_id, misconception_label = _misconception(
                    question,
                    assessment_type,
                    snapshot.selected_answer,
                    snapshot.selected_option,
                )

            for concept_id in concept_ids:
                evidence_id = _stable_id("evidence", submission_id, index, concept_id)
                evidence = MasteryEvidence(
                    evidence_id=evidence_id,
                    user_id=user_id,
                    submission_id=submission_id,
                    session_id=session_id,
                    question_id=_question_id(question, session_id, index),
                    concept_id=concept_id,
                    concept_label=_concept_label(question, concept_id, source_topic),
                    correct=feedback.correct,
                    difficulty=difficulty,
                    misconception_id=misconception_id,
                    misconception_label=misconception_label,
                    prerequisite_concept_ids=prerequisite_ids,
                    observed_at=observed_at,
                )
                self._repository.add_evidence(evidence)
                all_evidence = self._repository.list_evidence(user_id, concept_id)
                mastery = calculate_mastery(all_evidence)
                self._repository.save_mastery(mastery)
                decision = choose_adaptation(
                    mastery,
                    evidence,
                    decision_id=_stable_id("decision", evidence_id),
                    target_objective_ids=objective_ids,
                )
                self._repository.save_decision(decision)
                result.mastery_updates.append(mastery)
                result.decisions.append(decision)

        return result
