from __future__ import annotations

import datetime
import re
from typing import Any

from bson import ObjectId


ACTIVITY_TYPES = ("material", "video", "flashcards", "assessment")
MANUAL_ACTIVITY_TYPES = {"material", "flashcards"}


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
        unlocked = {
            item["module_id"]
            for item in self.db.course_module_unlocks.find(
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
        assessed_module_ids = self._assessed_module_ids(user_id, session_id)
        latest_assessment_by_module = {}
        for submission in self.db.assessment_submissions.find(
            {"user_id": user_id, "session_id": session_id},
            {"module_id": 1, "created_at": 1},
        ).sort("created_at", -1):
            module_id = submission.get("module_id")
            if module_id and str(module_id) not in latest_assessment_by_module:
                latest_assessment_by_module[str(module_id)] = str(submission["_id"])
        mastery = {
            item["concept_id"]: item
            for item in self.db.concept_mastery.find(
                {"user_id": user_id, "concept_id": {"$in": self._concept_ids(modules)}}
            )
        }

        public_modules: list[dict[str, Any]] = []
        previous_complete = True
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
                    completed = module_id in assessed_module_ids
                    activity["latest_submission_id"] = latest_assessment_by_module.get(module_id)
                activity["status"] = "completed" if completed else "todo"

            completed_count = sum(item["status"] == "completed" for item in activities)
            module_complete = bool(activities) and completed_count == len(activities)
            available = index == 0 or previous_complete or module_id in unlocked
            status = "completed" if module_complete else "active" if available else "locked"
            module_mastery = self._module_mastery(module, mastery)
            public_modules.append(
                {
                    "module_id": module_id,
                    "title": module.get("title") or f"Module {index + 1}",
                    "description": self._module_description(module),
                    "estimated_minutes": int(module.get("estimated_minutes") or 30),
                    "status": status,
                    "completed_activities": completed_count,
                    "total_activities": len(activities),
                    "progress_percent": round(completed_count / len(activities) * 100) if activities else 0,
                    "mastery_percent": module_mastery,
                    "needs_review": module_complete and module_mastery is not None and module_mastery < 65,
                    "activities": activities,
                }
            )
            previous_complete = module_complete

        activities = [item for module in public_modules for item in module["activities"]]
        completed = sum(item["status"] == "completed" for item in activities)
        percentage = round(completed / len(activities) * 100) if activities else 0
        current = next((module for module in public_modules if module["status"] == "active"), None)
        return {
            "session_id": str(session_id),
            "topic": session_data.get("topic") or "Untitled course",
            "difficulty": session_data.get("difficulty_level") or "medium",
            "status": "completed" if percentage == 100 and activities else "in_progress" if completed else "not_started",
            "progress_percent": percentage,
            "completed_activities": completed,
            "total_activities": len(activities),
            "completed_modules": sum(module["status"] == "completed" for module in public_modules),
            "total_modules": len(public_modules),
            "current_module_id": current["module_id"] if current else None,
            "current_module_title": current["title"] if current else None,
            "modules": public_modules,
        }

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

    def _assessed_module_ids(self, user_id, session_id):
        # Fetch all assessment submissions for this user and session
        submissions = list(self.db.assessment_submissions.find(
            {"user_id": user_id, "session_id": session_id},
            {"module_id": 1, "assessment_type": 1, "score": 1, "total": 1}
        ))
        
        module_scores = {}
        for sub in submissions:
            module_id = sub.get("module_id")
            if not module_id:
                continue
            
            atype = str(sub.get("assessment_type") or "")
            score = sub.get("score") or 0
            total = sub.get("total") or 1
            if total == 0:
                continue
                
            percent = (score / total) * 100
            
            if module_id not in module_scores:
                module_scores[module_id] = {"mcq": 0, "truefalse": 0, "oneword": 0}
            
            if atype in module_scores[module_id]:
                module_scores[module_id][atype] = max(module_scores[module_id][atype], percent)
                
        # A module is only completed if the user has >= 50% in all three assessment types
        return {
            mod_id
            for mod_id, types in module_scores.items()
            if types.get("mcq", 0) >= 50 and types.get("truefalse", 0) >= 50 and types.get("oneword", 0) >= 50
        }

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
