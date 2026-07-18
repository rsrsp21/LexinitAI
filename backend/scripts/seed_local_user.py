from __future__ import annotations

import os
import sys
from pathlib import Path

from pymongo import MongoClient
from werkzeug.security import generate_password_hash


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import Config  # noqa: E402


DEFAULT_EMAIL = "local@lexinit.ai"
DEFAULT_PASSWORD = "local1234"


def main() -> int:
    email = os.environ.get("LOCAL_SEED_EMAIL", DEFAULT_EMAIL).strip().lower()
    password = os.environ.get("LOCAL_SEED_PASSWORD", DEFAULT_PASSWORD)
    name = os.environ.get("LOCAL_SEED_NAME", "Local Learner").strip() or "Local Learner"

    client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=8000)
    try:
        client.admin.command("ping")
        db = client[Config.MONGO_DB_NAME]
        db.users.update_one(
            {"email": email},
            {
                "$set": {
                    "email": email,
                    "name": name,
                    "password": generate_password_hash(password),
                    "verified": True,
                    "rate_limit": 0,
                    "first_submission_time": None,
                }
            },
            upsert=True,
        )
    finally:
        client.close()

    print(f"Seeded local user: {email}")
    if email == DEFAULT_EMAIL and password == DEFAULT_PASSWORD:
        print(f"Password: {DEFAULT_PASSWORD}")
    else:
        print("Password: value from LOCAL_SEED_PASSWORD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
