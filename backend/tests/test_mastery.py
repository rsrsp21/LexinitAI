from datetime import datetime, timedelta, timezone

import pytest

from backend.lexinit.domain.mastery import choose_adaptation
from backend.lexinit.domain.mastery.calculator import (
    calculate_mastery,
    current_mastery,
    retention,
)
from backend.lexinit.schemas.adaptive import AdaptiveAction, MasteryBand, MasteryEvidence

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def evidence(
    index,
    correct,
    *,
    difficulty="medium",
    question=None,
    days=0.0,
    guess=0.0,
    kind="assessment",
    prerequisites=None,
    misconception=None,
):
    return MasteryEvidence(
        evidence_id=f"e{index}",
        user_id="user",
        submission_id="submission",
        session_id="session",
        question_id=question or f"q{index}",
        concept_id="concept",
        concept_label="Concept",
        correct=correct,
        difficulty=difficulty,
        observed_at=START + timedelta(days=days),
        source_kind=kind,
        guess_probability=guess,
        prerequisite_concept_ids=prerequisites or [],
        misconception_id=misconception,
    )


def probability(items):
    return calculate_mastery(items).mastery_probability


def test_no_evidence_is_rejected():
    with pytest.raises(ValueError):
        calculate_mastery([])


def test_missing_an_easy_question_hurts_more_than_missing_a_hard_one():
    assert probability([evidence(1, False, difficulty="easy")]) < probability(
        [evidence(1, False, difficulty="hard")]
    )


def test_a_hard_correct_answer_counts_more_than_an_easy_one():
    assert probability([evidence(1, True, difficulty="hard")]) > probability(
        [evidence(1, True, difficulty="easy")]
    )


def test_guessable_formats_count_for_less_when_correct():
    true_false = [evidence(i, True, guess=0.5) for i in range(4)]
    recalled = [evidence(i, True) for i in range(4)]
    assert probability(true_false) < probability(recalled)


def test_guessing_does_not_soften_a_wrong_answer():
    assert probability([evidence(1, False, guess=0.5)]) == probability([evidence(1, False)])


def test_repeating_a_seen_question_counts_for_less():
    repeated = [evidence(i, True, question="same", days=i * 0.01) for i in range(6)]
    distinct = [evidence(i, True, days=i * 0.01) for i in range(6)]
    assert probability(repeated) < probability(distinct)


def test_a_question_seen_long_ago_is_not_discounted():
    spaced = [evidence(0, True, question="same"), evidence(1, True, question="same", days=30)]
    crammed = [evidence(0, True, question="same"), evidence(1, True, question="same", days=0.01)]
    assert calculate_mastery(spaced).alpha > calculate_mastery(crammed).alpha


def test_recent_answers_outweigh_old_ones():
    old_mistakes = [evidence(i, False) for i in range(8)]
    recent_successes = [evidence(10 + i, True, days=90) for i in range(5)]
    mastery = calculate_mastery(old_mistakes + recent_successes)
    assert mastery.band is not MasteryBand.WEAK
    assert mastery.mastery_probability > 0.5


def test_confidence_grows_with_evidence():
    one = calculate_mastery([evidence(1, True)])
    many = calculate_mastery([evidence(i, True, days=i * 0.01) for i in range(10)])
    assert one.confidence < many.confidence <= 0.95


def test_retention_is_full_after_practice_and_ninety_percent_when_due():
    last = START
    due = START + timedelta(days=7)
    assert retention(last, due, last) == 1.0
    assert retention(last, due, due) == pytest.approx(0.9, abs=0.001)
    assert retention(last, due, START + timedelta(days=60)) < 0.6


def test_current_mastery_never_exceeds_stored_mastery():
    mastery = calculate_mastery([evidence(i, True, days=i * 0.01) for i in range(6)])
    later = mastery.last_practiced_at + timedelta(days=30)
    assert current_mastery(mastery, later) < mastery.mastery_probability


def test_one_wrong_answer_asks_for_more_evidence_not_remediation():
    item = evidence(1, False, prerequisites=["prerequisite"])
    decision = choose_adaptation(calculate_mastery([item]), item, decision_id="d")
    assert decision.action is AdaptiveAction.TARGETED_PRACTICE
    assert decision.reason_codes == ["insufficient_evidence"]


def test_a_strong_learner_who_slips_is_not_sent_back_to_prerequisites():
    items = [evidence(i, True, difficulty="hard") for i in range(8)]
    slip = evidence(99, False, prerequisites=["prerequisite"], days=1)
    decision = choose_adaptation(calculate_mastery(items + [slip]), slip, decision_id="d")
    assert decision.action is not AdaptiveAction.PREREQUISITE_REMEDIATION


def test_a_weak_learner_with_prerequisites_is_sent_back():
    items = [evidence(i, False, prerequisites=["prerequisite"], days=i * 0.1) for i in range(4)]
    decision = choose_adaptation(calculate_mastery(items), items[-1], decision_id="d")
    assert decision.action is AdaptiveAction.PREREQUISITE_REMEDIATION
    assert decision.target_concept_ids == ["prerequisite"]


def test_a_repeated_misconception_gets_a_correction():
    items = [evidence(i, False, misconception="mixes-up-x-and-y", days=i * 0.1) for i in range(2)]
    decision = choose_adaptation(calculate_mastery(items), items[-1], decision_id="d")
    assert decision.action is AdaptiveAction.MISCONCEPTION_CORRECTION
