"""Does the mastery estimate predict the learner's next answer?

For every answer, the script computes mastery from the answers *before* it and
treats that as the predicted chance of answering correctly. It then scores the
predictions against what actually happened.

Scores (lower is better for the first two):
  Brier     mean squared error of the predicted probability
  log loss  penalises confident wrong predictions heavily
  AUC       how well predictions rank right answers above wrong ones (0.5 = chance)

The mastery estimate is compared with two baselines: always predicting 50%,
and the learner's running average so far.

Usage (from the repository root):
  python -m backend.scripts.evaluate_mastery --simulate          # synthetic learners
  python -m backend.scripts.evaluate_mastery                     # real evidence in MongoDB
"""

from __future__ import annotations

import argparse
import math
import random
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from backend.lexinit.domain.mastery.calculator import calculate_mastery, retention
from backend.lexinit.schemas.adaptive import MasteryEvidence

GUESS = {"mcq": 0.25, "truefalse": 0.5, "oneword": 0.0}
DIFFICULTY_SHIFT = {"easy": 0.15, "medium": 0.0, "hard": -0.15}


def simulate(learners: int, answers: int, seed: int) -> dict[tuple[str, str], list[MasteryEvidence]]:
    """Synthetic learners with a hidden skill that grows with practice and
    decays between sessions, answering guessable questions of mixed difficulty."""
    rng = random.Random(seed)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sequences: dict[tuple[str, str], list[MasteryEvidence]] = {}
    for learner in range(learners):
        skill = rng.uniform(0.1, 0.7)
        learning_rate = rng.uniform(0.01, 0.08)
        moment = start
        items = []
        for index in range(answers):
            gap_days = rng.choice([0.01, 0.01, 0.02, 1, 3, 10, 30])
            moment += timedelta(days=gap_days)
            skill = max(0.05, skill - 0.004 * gap_days)  # forgetting
            kind = rng.choice(list(GUESS))
            difficulty = rng.choice(list(DIFFICULTY_SHIFT))
            knows = min(0.98, max(0.02, skill + DIFFICULTY_SHIFT[difficulty]))
            chance = knows * 0.95 + (1 - knows) * GUESS[kind]  # 5% slips, plus guessing
            correct = rng.random() < chance
            items.append(
                MasteryEvidence(
                    evidence_id=f"sim-{learner}-{index}",
                    user_id=f"learner-{learner}",
                    submission_id="simulation",
                    session_id="simulation",
                    question_id=f"q-{learner}-{index}",
                    concept_id="concept",
                    concept_label="Simulated concept",
                    correct=correct,
                    difficulty=difficulty,
                    observed_at=moment,
                    guess_probability=GUESS[kind],
                )
            )
            skill = min(0.97, skill + learning_rate * (1 - skill))  # practice
        sequences[(f"learner-{learner}", "concept")] = items
    return sequences


def load_from_database() -> dict[tuple[str, str], list[MasteryEvidence]]:
    from backend import create_app
    from backend.extensions import mongo

    app = create_app(resume_generation_runs=False)
    sequences: dict[tuple[str, str], list[MasteryEvidence]] = defaultdict(list)
    with app.app_context():
        for document in mongo.db.mastery_evidence.find().sort("observed_at", 1):
            payload = dict(document)
            payload.pop("_id", None)
            payload["user_id"] = str(payload["user_id"])
            item = MasteryEvidence.model_validate(payload)
            sequences[(item.user_id, item.concept_id)].append(item)
    return dict(sequences)


def predictions(sequences) -> list[tuple[float, float, float, bool]]:
    """(mastery prediction, running-average prediction, 0.5, outcome) per answer."""
    rows = []
    for items in sequences.values():
        for index in range(1, len(items)):
            history, target = items[:index], items[index]
            mastery = calculate_mastery(history, as_of=target.observed_at)
            remembered = retention(mastery.last_practiced_at, mastery.next_review_at, target.observed_at)
            knows = mastery.mastery_probability * remembered
            # A learner who does not know can still guess right.
            predicted = knows + (1 - knows) * target.guess_probability
            average = sum(item.correct for item in history) / len(history)
            rows.append((predicted, average, 0.5, target.correct))
    return rows


def brier(pairs):
    return sum((p - float(y)) ** 2 for p, y in pairs) / len(pairs)


def log_loss(pairs):
    total = 0.0
    for p, y in pairs:
        p = min(1 - 1e-6, max(1e-6, p))
        total += -math.log(p if y else 1 - p)
    return total / len(pairs)


def auc(pairs):
    positives = [p for p, y in pairs if y]
    negatives = [p for p, y in pairs if not y]
    if not positives or not negatives:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in positives for n in negatives)
    return wins / (len(positives) * len(negatives))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--simulate", action="store_true", help="use synthetic learners instead of MongoDB")
    parser.add_argument("--learners", type=int, default=300)
    parser.add_argument("--answers", type=int, default=30)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    sequences = simulate(args.learners, args.answers, args.seed) if args.simulate else load_from_database()
    rows = predictions(sequences)
    if not rows:
        print("Not enough evidence yet: each concept needs at least two answers.")
        return

    source = "simulated learners" if args.simulate else "real evidence"
    print(f"{len(rows)} predictions from {len(sequences)} learner-concept histories ({source})")
    print(f"{'model':<18}{'Brier':>8}{'log loss':>10}{'AUC':>8}")
    for name, column in (("mastery estimate", 0), ("running average", 1), ("always 50%", 2)):
        pairs = [(row[column], row[3]) for row in rows]
        print(f"{name:<18}{brier(pairs):>8.4f}{log_loss(pairs):>10.4f}{auc(pairs):>8.3f}")
    if not args.simulate and len(rows) < 200:
        print("Fewer than 200 predictions: treat these numbers as a rough indication only.")


if __name__ == "__main__":
    main()
