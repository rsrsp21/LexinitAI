from __future__ import annotations

import datetime
import re
from typing import Any

from bson import ObjectId

from backend.lexinit.domain.assessment import questions_for_assessment
from backend.lexinit.schemas.assessment import AssessmentType
from backend.lexinit.services.final_assessment import final_assessment_state


ACTIVITY_TYPES = ("material", "video", "flashcards", "assessment")
MANUAL_ACTIVITY_TYPES = {"material", "flashcards"}
ASSESSMENT_TYPE_ORDER = (
    AssessmentType.MCQ.value,
    AssessmentType.TRUE_FALSE.value,
    AssessmentType.ONE_WORD.value,
)
# Learners need at least this score on every assessment type in a module to
# pass it and unlock the next module.
ASSESSMENT_PASS_PERCENT = 50


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


class CourseProgressService:
    def __init__(self, db):
        self.db = db

    def course(self, user_id: ObjectId, session_data: dict[str, Any]) -> dict[str, Any]:
        session_id = session_data["_id"]
        curriculum = session_data.get("curriculum") or {}
        modules = list(curriculum.get("modules") or [])
        if not modules:
            modules = self._fallback_modules(session_data)

        saved = {
            item["activity_id"]: item
            for item in self.db.course_activity_progress.find(
                {"user_id": user_id, "session_id": session_id}
            )
        }
        completed_video_ids = {
            item["video_id"]
            for item in self.db.video_progress.find(
                {
                    "user_id": user_id,
                    "session_id": session_id,
                    "completed_at": {"$ne": None},
                }
            )
        }
        module_order = [
            str(module.get("module_id") or f"module_{index + 1}")
            for index, module in enumerate(modules)
        ]
        question_counts = _assessment_question_counts(session_data, module_order)
        assessment_results = self._assessment_results(user_id, session_id)
        mastery = {
            item["concept_id"]: item
            for item in self.db.concept_mastery.find(
                {"user_id": user_id, "concept_id": {"$in": self._concept_ids(modules)}}
            )
        }

        public_modules: list[dict[str, Any]] = []
        for index, module in enumerate(modules):
            module_id = str(module.get("module_id") or f"module_{index + 1}")
            activities = self._activities(session_data, module, index)
            for activity in activities:
                record = saved.get(activity["activity_id"])
                completed = bool(record and record.get("status") == "completed")
                if activity["type"] == "video":
                    video_ids = set(activity.pop("video_ids", []))
                    completed = bool(video_ids) and video_ids.issubset(completed_video_ids)
                elif activity["type"] == "assessment":
                    types = _module_assessment_types(
                        question_counts.get(module_id, {}),
                        assessment_results.get(module_id, {}),
                    )
                    activity["assessment_types"] = types
                    completed = bool(types) and all(item["passed"] for item in types)
                    latest = max(
                        (item for item in types if item["latest_submission_id"]),
                        key=lambda item: item["latest_at"] or "",
                        default=None,
                    )
                    activity["latest_submission_id"] = (
                        latest["latest_submission_id"] if latest else None
                    )
                activity["status"] = "completed" if completed else "todo"

            completed_count = sum(item["status"] == "completed" for item in activities)
            module_complete = bool(activities) and completed_count == len(activities)
            assessment = next((item for item in activities if item["type"] == "assessment"), None)
            # Every module is open; passing the module assessment (or finishing
            # every activity when there is none) marks where to go next.
            module_passed = assessment["status"] == "completed" if assessment else module_complete
            status = "completed" if module_complete else "active"
            module_mastery = self._module_mastery(module, mastery)
            public_modules.append(
                {
                    "module_id": module_id,
                    "title": module.get("title") or f"Module {index + 1}",
                    "description": self._module_description(module),
                    "estimated_minutes": int(module.get("estimated_minutes") or 30),
                    "status": status,
                    "passed": module_passed,
                    "completed_activities": completed_count,
                    "total_activities": len(activities),
                    "progress_percent": round(completed_count / len(activities) * 100) if activities else 0,
                    "mastery_percent": module_mastery,
                    "needs_review": module_complete and module_mastery is not None and module_mastery < 65,
                    "activities": activities,
                }
            )

        activities = [item for module in public_modules for item in module["activities"]]
        completed = sum(item["status"] == "completed" for item in activities)
        total = len(activities)
        # Courses with assessments end in a final assessment. It counts as the
        # last step, so a course is only complete (and earns its badge) once
        # the final is passed.
        final = self._final_assessment(user_id, session_id, public_modules)
        if final["required"]:
            total += 1
            completed += 1 if final["passed"] else 0
        percentage = round(completed / total * 100) if total else 0
        if percentage == 100 and completed < total:
            percentage = 99
        # The recommended module is the first one not yet passed.
        current = next((module for module in public_modules if not module["passed"]), None)
        return {
            "session_id": str(session_id),
            "topic": session_data.get("topic") or "Untitled course",
            "difficulty": session_data.get("difficulty_level") or "medium",
            "status": "completed" if total and completed == total else "in_progress" if completed else "not_started",
            "progress_percent": percentage,
            "completed_activities": completed,
            "total_activities": total,
            "final_assessment": final,
            "completed_modules": sum(module["status"] == "completed" for module in public_modules),
            "total_modules": len(public_modules),
            "current_module_id": current["module_id"] if current else None,
            "current_module_title": current["title"] if current else None,
            "modules": public_modules,
        }

    def _final_assessment(self, user_id, session_id, public_modules):
        required = any(
            activity["type"] == "assessment"
            for module in public_modules
            for activity in module["activities"]
        )
        if not required:
            return {"required": False, "passed": False, "state": "not_required"}
        state = final_assessment_state(self.db, user_id, session_id)
        modules_passed = all(module["passed"] for module in public_modules)
        if state["passed"]:
            label = "passed"
        elif state["active_final_id"]:
            label = "in_progress"
        elif not modules_passed:
            label = "locked"
        elif state["retry_available_at"]:
            label = "cooldown"
        else:
            label = "available"
        return {"required": True, "state": label, **state}

    def set_activity_status(
        self,
        user_id: ObjectId,
        session_data: dict[str, Any],
        activity_id: str,
        status: str,
    ) -> dict[str, Any]:
        course = self.course(user_id, session_data)
        activity = next(
            (
                item
                for module in course["modules"]
                for item in module["activities"]
                if item["activity_id"] == activity_id
            ),
            None,
        )
        if not activity:
            raise ValueError("Unknown course activity.")
        if activity["type"] not in MANUAL_ACTIVITY_TYPES:
            raise ValueError("This activity is completed from learning evidence.")
        if status not in {"todo", "completed"}:
            raise ValueError("Invalid activity status.")
        now = utcnow()
        self.db.course_activity_progress.update_one(
            {
                "user_id": user_id,
                "session_id": session_data["_id"],
                "activity_id": activity_id,
            },
            {
                "$set": {
                    "user_id": user_id,
                    "session_id": session_data["_id"],
                    "module_id": activity["module_id"],
                    "activity_id": activity_id,
                    "activity_type": activity["type"],
                    "status": status,
                    "updated_at": now,
                    "completed_at": now if status == "completed" else None,
                }
            },
            upsert=True,
        )
        return self.course(user_id, session_data)

    def unlock_module(self, user_id: ObjectId, session_data: dict[str, Any], module_id: str):
        course = self.course(user_id, session_data)
        module = next((item for item in course["modules"] if item["module_id"] == module_id), None)
        if not module:
            raise ValueError("Unknown course module.")
        self.db.course_module_unlocks.update_one(
            {"user_id": user_id, "session_id": session_data["_id"], "module_id": module_id},
            {"$set": {"user_id": user_id, "session_id": session_data["_id"], "module_id": module_id, "created_at": utcnow()}},
            upsert=True,
        )
        return self.course(user_id, session_data)

    def summaries(self, user_id: ObjectId, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {key: value for key, value in self.course(user_id, item).items() if key != "modules"}
            | {"created_at": _serialize_date(item.get("created_at"))}
            for item in sessions
        ]

    def _activities(self, session_data, module, index):
        module_id = str(module.get("module_id") or f"module_{index + 1}")
        concept_ids = {item.get("concept_id") for item in module.get("concepts") or []}
        activities = []
        definitions = [
            ("material", "Study the materials", "Build a clear foundation before practice.", "materials"),
            ("video", "Watch the video lecture", "See the concept explained step by step.", "videos"),
            ("flashcards", "Review flashcards", "Strengthen recall of the key ideas.", "flashcards"),
            ("assessment", "Check your understanding", "Use a short assessment to verify learning.", "assessments"),
        ]
        for activity_type, title, detail, route in definitions:
            items = self._module_items(session_data, module_id, concept_ids, index, activity_type)
            if not items:
                continue
            activity = {
                "activity_id": f"{module_id}:{activity_type}",
                "module_id": module_id,
                "type": activity_type,
                "title": title,
                "detail": detail,
                "item_count": len(items),
                "route": route,
            }
            if activity_type == "video":
                activity["video_ids"] = [video_id for item in items if (video_id := _video_id(item))]
            activities.append(activity)
        return activities

    def _module_items(self, session_data, module_id, concept_ids, index, activity_type):
        field_map = {
            "material": "study_materials",
            "video": "course_content",
            "flashcards": "flashcards",
        }
        if activity_type == "assessment":
            items = []
            for field in ("mcqs", "mcq", "mcq_questions", "true_false", "truefalse", "true_false_questions", "oneword", "one_word", "oneword_questions", "one_word_questions"):
                items.extend(session_data.get(field) or [])
        else:
            items = list(session_data.get(field_map[activity_type]) or [])
        matched = [item for item in items if isinstance(item, dict) and _matches_module(item, module_id, concept_ids)]
        if matched:
            return matched
        if index < len(items):
            return [items[index]]
        return []

    def _assessment_results(self, user_id, session_id):
        """Best and latest result per module and assessment type."""
        submissions = list(
            self.db.assessment_submissions.find(
                {"user_id": user_id, "session_id": session_id},
                {
                    "module_id": 1,
                    "attempt_id": 1,
                    "assessment_type": 1,
                    "score": 1,
                    "total": 1,
                    "created_at": 1,
                },
            ).sort("created_at", 1)
        )
        # Older submissions did not store their module; recover it from the attempt.
        missing_attempt_ids = []
        for submission in submissions:
            if not submission.get("module_id") and submission.get("attempt_id"):
                try:
                    missing_attempt_ids.append(ObjectId(submission["attempt_id"]))
                except Exception:
                    continue
        attempt_modules = {}
        if missing_attempt_ids:
            attempt_modules = {
                str(item["_id"]): item.get("module_id")
                for item in self.db.assessment_attempts.find(
                    {"_id": {"$in": missing_attempt_ids}, "user_id": user_id},
                    {"module_id": 1},
                )
            }

        results: dict[str, dict[str, dict[str, Any]]] = {}
        for submission in submissions:
            module_id = submission.get("module_id") or attempt_modules.get(
                str(submission.get("attempt_id") or "")
            )
            assessment_type = str(submission.get("assessment_type") or "")
            total = int(submission.get("total") or 0)
            if not module_id or assessment_type not in ASSESSMENT_TYPE_ORDER or total <= 0:
                continue
            score = int(submission.get("score") or 0)
            percent = round(score / total * 100)
            entry = results.setdefault(str(module_id), {}).setdefault(
                assessment_type, {"best_percent": 0, "attempts": 0}
            )
            entry["attempts"] += 1
            entry["best_percent"] = max(entry["best_percent"], percent)
            entry["latest_submission_id"] = str(submission["_id"])
            entry["latest_score"] = score
            entry["latest_total"] = total
            entry["latest_at"] = _serialize_date(submission.get("created_at"))
        return results

    @staticmethod
    def _concept_ids(modules):
        return [item.get("concept_id") for module in modules for item in module.get("concepts") or [] if item.get("concept_id")]

    @staticmethod
    def _module_mastery(module, mastery):
        values = [mastery[item.get("concept_id")].get("mastery_probability", 0) for item in module.get("concepts") or [] if item.get("concept_id") in mastery]
        return round(sum(values) / len(values) * 100) if values else None

    @staticmethod
    def _module_description(module):
        objectives = module.get("learning_objectives") or []
        return objectives[0].get("description") if objectives else "Learn, recall, and check your understanding."

    @staticmethod
    def _fallback_modules(session_data):
        return [
            {"module_id": f"module_{index + 1}", "title": title, "concepts": [], "learning_objectives": [], "estimated_minutes": 30}
            for index, title in enumerate(session_data.get("subtopics") or [])
        ]


def _assessment_question_counts(session_data, module_order):
    """Count questions per module and type, using the same module assignment as
    the private question bank (explicit module_id, else round-robin)."""
    counts: dict[str, dict[str, int]] = {}
    for assessment_type in AssessmentType:
        try:
            questions = questions_for_assessment(session_data, assessment_type)
        except Exception:
            continue
        for index, question in enumerate(questions):
            module_id = question.get("module_id") or (
                module_order[index % len(module_order)] if module_order else None
            )
            if module_id:
                bucket = counts.setdefault(str(module_id), {})
                bucket[assessment_type.value] = bucket.get(assessment_type.value, 0) + 1
    return counts


def _module_assessment_types(question_counts, results):
    types = []
    for assessment_type in ASSESSMENT_TYPE_ORDER:
        count = question_counts.get(assessment_type, 0)
        if not count:
            continue
        result = results.get(assessment_type, {})
        best = result.get("best_percent")
        types.append(
            {
                "type": assessment_type,
                "question_count": count,
                "attempts": result.get("attempts", 0),
                "best_percent": best,
                "passed": best is not None and best >= ASSESSMENT_PASS_PERCENT,
                "latest_submission_id": result.get("latest_submission_id"),
                "latest_score": result.get("latest_score"),
                "latest_total": result.get("latest_total"),
                "latest_at": result.get("latest_at"),
            }
        )
    return types


def _matches_module(item, module_id, concept_ids):
    if item.get("module_id") == module_id:
        return True
    return bool(concept_ids.intersection(item.get("concept_ids") or []))


def _video_id(item):
    if item.get("video_id"):
        return item["video_id"]
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", str(item.get("link") or item.get("url") or ""))
    return match.group(1) if match else None


def _serialize_date(value):
    return value.isoformat() if hasattr(value, "isoformat") else value
