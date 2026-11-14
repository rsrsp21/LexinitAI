"""Rate limiting, answer-key verification and public course payloads."""

from backend.lexinit.security import (
    RedisRateLimiter,
    SlidingWindowRateLimiter,
    _is_coach_generation,
    _starts_generation,
)
from backend.lexinit.services.question_quality import SolvedQuestion, SolvedSet, verify_answer_keys
from backend.routes.api import PRIVATE_QUESTION_KEYS, _public_session


def test_sliding_window_blocks_after_the_limit_and_recovers():
    limiter = SlidingWindowRateLimiter()
    results = [limiter.check("key", limit=3, window_seconds=60, now=float(second)) for second in range(4)]
    assert results[:3] == [0, 0, 0]
    assert results[3] > 0
    assert limiter.check("key", limit=3, window_seconds=60, now=61.0) == 0


def test_limits_are_separate_per_key():
    limiter = SlidingWindowRateLimiter()
    assert limiter.check("a", limit=1, window_seconds=60, now=0.0) == 0
    assert limiter.check("b", limit=1, window_seconds=60, now=0.0) == 0
    assert limiter.check("a", limit=1, window_seconds=60, now=1.0) > 0


def test_redis_limiter_falls_back_when_redis_is_down():
    class BrokenRedis:
        def register_script(self, _script):
            def run(**_kwargs):
                raise ConnectionError("redis unavailable")

            return run

    limiter = RedisRateLimiter(BrokenRedis())
    assert [limiter.check("key", limit=2, window_seconds=60) for _ in range(3)][:2] == [0, 0]
    assert limiter.check("key", limit=2, window_seconds=60) > 0


def test_every_path_that_starts_generation_shares_the_start_limit():
    for path in (
        "/submit-topic",
        "/api/v1/generation-runs",
        "/api/v1/sessions/abc/regenerate",
        "/api/sessions/abc/regenerate",
        "/api/v1/generation-runs/abc/retry",
        "/api/generation-jobs/abc/retry",
    ):
        assert _starts_generation(path), path
    assert not _starts_generation("/api/v1/sessions/abc/course")


def test_ai_backed_coach_calls_are_limited_but_answers_are_not():
    assert _is_coach_generation("/api/v1/coach/practice")
    assert _is_coach_generation("/api/v1/sessions/abc/final-assessment")
    assert _is_coach_generation("/api/v1/coach/sessions/abc/modules/m1/pre-check")
    assert not _is_coach_generation("/api/v1/coach/checks/check_1/answer")


class FakeSolver:
    def __init__(self, answers):
        self._answers = answers

    def generate_structured(self, prompt, schema, *, temperature=0.2):
        return SolvedSet(answers=[SolvedQuestion(**item) for item in self._answers])


def test_questions_with_a_disputed_answer_key_are_dropped():
    questions = [
        {"type": "mcq", "question": "7 x 8?", "options": ["54", "56", "58", "64"], "answer": 1},
        {"type": "mcq", "question": "Capital of France?", "options": ["Paris", "Lyon", "Nice", "Lille"], "answer": 2},
        {"type": "truefalse", "question": "The Earth orbits the Sun.", "answer": True},
        {"type": "truefalse", "question": "Unclear statement.", "answer": True},
    ]
    solver = FakeSolver(
        [
            {"index": 0, "answer": "B"},
            {"index": 1, "answer": "A"},
            {"index": 2, "answer": "true"},
            {"index": 3, "answer": "true", "ambiguous": True},
        ]
    )
    kept = verify_answer_keys(solver, questions)
    assert [item["question"] for item in kept] == ["7 x 8?", "The Earth orbits the Sun."]


def test_one_word_keys_accept_synonyms_and_record_alternatives():
    questions = [
        {"type": "oneword", "question": "Molecule that stores genes?", "answer": "deoxyribonucleic-acid"}
    ]
    solver = FakeSolver([{"index": 0, "answer": "DNA", "alternatives": ["deoxyribonucleic-acid"]}])
    kept = verify_answer_keys(solver, questions)
    assert len(kept) == 1
    assert kept[0]["accepted_answers"] == ["DNA"]


def test_a_one_word_key_the_solver_rejects_is_dropped():
    questions = [{"type": "oneword", "question": "Powerhouse of the cell?", "answer": "nucleus"}]
    solver = FakeSolver([{"index": 0, "answer": "mitochondria"}])
    assert verify_answer_keys(solver, questions) == []


def test_questions_are_kept_when_the_check_itself_fails():
    class FailingSolver:
        def generate_structured(self, *args, **kwargs):
            raise RuntimeError("model unavailable")

    questions = [{"type": "truefalse", "question": "Anything.", "answer": True}]
    assert verify_answer_keys(FailingSolver(), questions) == questions


def test_course_payload_never_carries_answers():
    course = {
        "_id": "course",
        "mcqs": [
            {
                "question": "Q",
                "options": ["a", "b", "c", "d"],
                "answer": 2,
                "explanation": "because",
                "misconception_map": {"A": "x", "B": "y", "D": "z"},
            }
        ],
        "oneword": [{"question": "Q", "answer": "word", "accepted_answers": ["term"]}],
    }
    public = _public_session(course)
    for field in ("mcqs", "oneword"):
        for question in public[field]:
            assert not PRIVATE_QUESTION_KEYS.intersection(question)
    assert public["mcqs"][0]["options"] == ["a", "b", "c", "d"]
