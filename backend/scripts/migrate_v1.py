"""Additive historical-data migration for the v1 API contracts.

Run a dry audit first:
    uv run --project backend python -m backend.scripts.migrate_v1

Apply after a verified database backup:
    uv run --project backend python -m backend.scripts.migrate_v1 --apply
"""

from __future__ import annotations

import argparse
import datetime

from backend.app import app
from backend.db import migrate_embedded_sessions, normalize_topic_for_storage
from backend.extensions import mongo


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def migration_plan(db) -> dict[str, int]:
    return {
        "embedded_users": db.users.count_documents({"sessions.0": {"$exists": True}}),
        "sessions_without_api_version": db.sessions.count_documents(
            {"api_schema_version": {"$exists": False}}
        ),
        "runs_without_api_version": db.generation_runs.count_documents(
            {"api_schema_version": {"$exists": False}}
        ),
        "submissions_without_api_version": db.assessment_submissions.count_documents(
            {"api_schema_version": {"$exists": False}}
        ),
    }


def apply_migration(db) -> dict[str, int]:
    migrate_embedded_sessions(db)
    migrated_at = utcnow()
    for session in db.sessions.find(
        {"api_schema_version": {"$exists": False}},
        {"topic": 1, "mode": 1, "generation_mode": 1, "difficulty_level": 1},
    ):
        changes = {
            "api_schema_version": 1,
            "migrated_at": migrated_at,
            "normalized_topic": normalize_topic_for_storage(session.get("topic")),
            "generation_mode": session.get("generation_mode") or session.get("mode") or "Basic",
        }
        if session.get("difficulty_level"):
            changes["difficulty_level"] = str(session["difficulty_level"]).strip().lower()
        db.sessions.update_one({"_id": session["_id"]}, {"$set": changes})
    db.generation_runs.update_many(
        {"api_schema_version": {"$exists": False}},
        {"$set": {"api_schema_version": 1, "migrated_at": migrated_at}},
    )
    db.assessment_submissions.update_many(
        {"api_schema_version": {"$exists": False}},
        {"$set": {"api_schema_version": 1, "migrated_at": migrated_at}},
    )
    return migration_plan(db)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply the additive migration.")
    args = parser.parse_args()
    with app.app_context():
        before = migration_plan(mongo.db)
        print({"mode": "apply" if args.apply else "dry-run", "before": before})
        if args.apply:
            after = apply_migration(mongo.db)
            print({"after": after})
        else:
            print("No data changed. Verify a backup, then rerun with --apply.")


if __name__ == "__main__":
    main()
