from __future__ import annotations

import datetime
import hashlib
import math
import re
from typing import Any

import isodate
from bson import ObjectId
from fuzzywuzzy import fuzz
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

from backend.lexinit.api.errors import ApiError
from backend.lexinit.domain.mastery import calculate_mastery, choose_adaptation
from backend.lexinit.repositories import MongoAdaptiveLearningRepository
from backend.lexinit.schemas import VideoPlaybackState, VideoStudyGuideContent
from backend.lexinit.schemas.adaptive import MasteryEvidence
from backend.lexinit.schemas.generation import Difficulty


CATALOG_VERSION = "video-catalog-v1"
TRANSCRIPT_VERSION = "youtube-transcript-v1"
GUIDE_VERSION = "video-guide-v1"
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def video_id_from_item(item: dict[str, Any]) -> str | None:
    candidate = item.get("video_id")
    if isinstance(candidate, str) and VIDEO_ID_RE.fullmatch(candidate):
        return candidate
    link = str(item.get("link") or item.get("url") or "")
    match = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", link)
    return match.group(1) if match else None


class VideoLearningService:
    def __init__(
        self,
        *,
        metadata_collection,
        transcript_collection,
        guide_collection,
        progress_collection,
        retrieval_collection,
        adaptive_repository: MongoAdaptiveLearningRepository,
        youtube_client=None,
        transcript_api=None,
        model=None,
    ) -> None:
        self._metadata = metadata_collection
        self._transcripts = transcript_collection
        self._guides = guide_collection
        self._progress = progress_collection
        self._retrieval = retrieval_collection
        self._adaptive = adaptive_repository
        self._youtube = youtube_client
        self._transcript_api = transcript_api or YouTubeTranscriptApi()
        self._model = model
        self._model_version = str(getattr(model, "model_name", "test-or-default"))

    def catalog(
        self,
        *,
        user_id: str,
        session_data: dict[str, Any],
        probe_transcripts: bool = False,
        hydrate_metadata: bool = False,
    ) -> dict[str, Any]:
        raw_items = [item for item in session_data.get("course_content", []) if isinstance(item, dict)]
        items = []
        for index, item in enumerate(raw_items):
            video_id = video_id_from_item(item)
            if not video_id:
                continue
            context = _video_context(session_data, item, index)
            items.append({**item, **context, "video_id": video_id})

        video_ids = list(dict.fromkeys(item["video_id"] for item in items))
        metadata = self._metadata_for(video_ids, refresh_missing=hydrate_metadata)
        if probe_transcripts:
            for video_id in video_ids:
                if metadata.get(video_id, {}).get("transcript_status") in {
                    None,
                    "unknown",
                    "unavailable",
                }:
                    status = self._probe_transcript(video_id)
                    metadata.setdefault(video_id, {})["transcript_status"] = status

        session_id = str(session_data.get("_id"))
        progress_docs = {
            item["video_id"]: item
            for item in self._progress.find(
                {
                    "user_id": ObjectId(user_id),
                    "session_id": session_data.get("_id"),
                    "video_id": {"$in": video_ids},
                }
            )
        }
        guide_video_ids = {
            item["video_id"]
            for item in self._guides.find(
                {
                    "session_id": session_id,
                    "video_id": {"$in": video_ids},
                    "schema_version": GUIDE_VERSION,
                },
                {"video_id": 1},
            )
        }
        public_items = []
        for item in items:
            details = metadata.get(item["video_id"], {})
            if details.get("embeddable") is False or details.get("made_for_kids") is True:
                continue
            progress = progress_docs.get(item["video_id"], {})
            duration_seconds = int(details.get("duration_seconds") or item.get("duration_seconds") or 0)
            recommendation_reason = item.get("recommendation_reason") or _recommendation_reason(item)
            public_items.append(
                {
                    "video_id": item["video_id"],
                    "title": details.get("title") or item.get("title") or item.get("subtopic") or "Video lecture",
                    "url": item.get("link") or item.get("url") or f"https://www.youtube.com/watch?v={item['video_id']}",
                    "channel": details.get("channel") or item.get("channel") or item.get("author") or "YouTube",
                    "thumbnail_url": details.get("thumbnail_url") or item.get("thumbnail_url"),
                    "duration_seconds": duration_seconds,
                    "transcript_status": details.get("transcript_status") or "unknown",
                    "module_id": item.get("module_id"),
                    "module_title": item.get("module_title") or item.get("subtopic") or "Video lectures",
                    "concept_ids": list(item.get("concept_ids") or []),
                    "objective_ids": list(item.get("objective_ids") or []),
                    "objective_labels": list(item.get("objective_labels") or []),
                    "coverage_labels": list(item.get("coverage_labels") or []),
                    "recommendation_reason": recommendation_reason,
                    "position_seconds": float(progress.get("position_seconds") or 0),
                    "furthest_position_seconds": float(progress.get("furthest_position_seconds") or 0),
                    "progress_percent": _progress_percent(progress, duration_seconds),
                    "completed": bool(progress.get("completed_at")),
                    "summary_status": "ready" if item["video_id"] in guide_video_ids else "not_requested",
                }
            )

        public_items.sort(key=lambda item: (_module_order(session_data, item.get("module_id")), -_rank(item), item["video_id"]))
        return {"session_id": session_id, "videos": public_items, "count": len(public_items)}

    def save_progress(
        self,
        *,
        user_id: str,
        session_data: dict[str, Any],
        video_id: str,
        position_seconds: float,
        duration_seconds: float,
        state: VideoPlaybackState,
    ) -> dict[str, Any]:
        self._require_video(session_data, video_id)
        now = utcnow()
        completed = state is VideoPlaybackState.ENDED and (
            position_seconds >= duration_seconds * 0.8 or duration_seconds - position_seconds <= 20
        )
        existing = self._progress.find_one(
            {
                "user_id": ObjectId(user_id),
                "session_id": session_data.get("_id"),
                "video_id": video_id,
            }
        )
        furthest = max(float(existing.get("furthest_position_seconds") or 0) if existing else 0, position_seconds)
        update = {
            "$set": {
                "position_seconds": round(position_seconds, 2),
                "furthest_position_seconds": round(furthest, 2),
                "duration_seconds": round(duration_seconds, 2),
                "state": state.value,
                "updated_at": now,
            },
            "$setOnInsert": {
                "user_id": ObjectId(user_id),
                "session_id": session_data.get("_id"),
                "video_id": video_id,
                "created_at": now,
            },
        }
        if completed:
            update["$set"]["completed_at"] = existing.get("completed_at") if existing else now
            if update["$set"]["completed_at"] is None:
                update["$set"]["completed_at"] = now
        document = self._progress.find_one_and_update(
            {
                "user_id": ObjectId(user_id),
                "session_id": session_data.get("_id"),
                "video_id": video_id,
            },
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return _public_progress(document)

    def study_guide(
        self,
        *,
        user_id: str,
        session_data: dict[str, Any],
        video_id: str,
    ) -> dict[str, Any]:
        del user_id  # Ownership is established by the caller's session lookup.
        item = self._require_video(session_data, video_id)
        context = _video_context(session_data, item, 0)
        guide_id = _guide_id(
            str(session_data.get("_id")),
            video_id,
            context,
            self._model_version,
        )
        existing = self._guides.find_one({"_id": guide_id})
        if existing:
            return _public_guide(existing)

        transcript = self._get_transcript(video_id)
        if transcript.get("status") != "available":
            return {
                "guide_id": guide_id,
                "video_id": video_id,
                "status": "unavailable",
                "transcript_status": transcript.get("status") or "unavailable",
                "retryable": bool(transcript.get("retryable")),
                "summary_points": [],
                "key_moments": [],
                "questions": [],
            }
        if self._model is None:
            raise ApiError(
                "Video summaries are temporarily unavailable.",
                status_code=503,
                code="video_summary_unavailable",
            )

        prompt = _guide_prompt(
            session_data,
            context,
            transcript["text"],
            transcript.get("segments") or [],
        )
        guide = self._model.generate_structured(
            prompt,
            VideoStudyGuideContent,
            temperature=0.1,
        )
        now = utcnow()
        document = {
            "_id": guide_id,
            "video_id": video_id,
            "session_id": str(session_data.get("_id")),
            "curriculum_id": session_data.get("curriculum_id") or (session_data.get("curriculum") or {}).get("curriculum_id"),
            "module_id": context.get("module_id"),
            "concept_ids": context.get("concept_ids") or [],
            "objective_ids": context.get("objective_ids") or [],
            "summary_points": list(guide.summary_points),
            "key_moments": [item.model_dump(mode="python") for item in guide.key_moments],
            "retrieval_questions": [item.model_dump(mode="python") for item in guide.retrieval_questions],
            "transcript_cache_id": transcript["_id"],
            "schema_version": GUIDE_VERSION,
            "model_version": self._model_version,
            "prompt_version": GUIDE_VERSION,
            "created_at": now,
        }
        try:
            self._guides.insert_one(document)
        except DuplicateKeyError:
            document = self._guides.find_one({"_id": guide_id}) or document
        return _public_guide(document)

    def submit_retrieval_check(
        self,
        *,
        user_id: str,
        session_data: dict[str, Any],
        video_id: str,
        guide_id: str,
        answers: list[str],
        idempotency_key: str,
    ) -> dict[str, Any]:
        self._require_video(session_data, video_id)
        progress = self._progress.find_one(
            {
                "user_id": ObjectId(user_id),
                "session_id": session_data.get("_id"),
                "video_id": video_id,
                "completed_at": {"$ne": None},
            }
        )
        if not progress:
            raise ApiError(
                "Complete the video before submitting its knowledge check.",
                status_code=409,
                code="video_not_completed",
            )
        guide = self._guides.find_one(
            {"_id": guide_id, "video_id": video_id, "session_id": str(session_data.get("_id"))}
        )
        if not guide:
            raise ApiError("Lecture Guide not found.", status_code=404, code="video_guide_not_found")
        questions = list(guide.get("retrieval_questions") or [])
        if len(answers) != len(questions) or any(not answer.strip() for answer in answers):
            raise ApiError(
                "Answer every retrieval question before submitting.",
                code="incomplete_video_retrieval_check",
            )

        event_id = f"video_retrieval_{_hash(user_id, idempotency_key)[:32]}"
        existing = self._retrieval.find_one({"_id": event_id, "user_id": ObjectId(user_id)})
        if existing:
            if existing.get("guide_id") != guide_id:
                raise ApiError(
                    "This idempotency key was already used for another video check.",
                    status_code=409,
                    code="idempotency_conflict",
                )
            return existing["public_result"]

        feedback = []
        correct_flags = []
        for answer, question in zip(answers, questions):
            correct = _answer_is_correct(answer, question)
            correct_flags.append(correct)
            feedback.append(
                {
                    "correct": correct,
                    "expected_answer": question["expected_answer"],
                    "explanation": question["explanation"],
                }
            )

        now = utcnow()
        concept_ids = list(guide.get("concept_ids") or []) or [f"video:{video_id}"]
        labels = _concept_labels(session_data)
        mastery_updates = []
        decisions = []
        overall_correct = sum(correct_flags) / len(correct_flags) >= 0.67
        for index, concept_id in enumerate(concept_ids):
            correct = overall_correct
            evidence = MasteryEvidence(
                evidence_id=f"evidence_{_hash(event_id, concept_id)[:32]}",
                user_id=user_id,
                submission_id=event_id,
                session_id=str(session_data.get("_id")),
                question_id=f"{guide_id}:{index % len(questions)}",
                concept_id=concept_id,
                concept_label=labels.get(concept_id, concept_id.replace("_", " ").title()),
                correct=correct,
                difficulty=_session_difficulty(session_data),
                observed_at=now,
                source_kind="video_retrieval",
                evidence_weight=0.75,
            )
            self._adaptive.add_evidence(evidence)
            mastery = calculate_mastery(self._adaptive.list_evidence(user_id, concept_id))
            self._adaptive.save_mastery(mastery)
            decision = choose_adaptation(
                mastery,
                evidence,
                decision_id=f"decision_{_hash(event_id, concept_id)[:32]}",
                target_objective_ids=list(guide.get("objective_ids") or []),
            )
            self._adaptive.save_decision(decision)
            mastery_updates.append(mastery.public_dict())
            decisions.append(decision.public_dict())

        result = {
            "event_id": event_id,
            "video_id": video_id,
            "score": sum(correct_flags),
            "total": len(correct_flags),
            "feedback": feedback,
            "mastery_updates": mastery_updates,
            "adaptation_decisions": decisions,
        }
        try:
            self._retrieval.insert_one(
                {
                    "_id": event_id,
                    "user_id": ObjectId(user_id),
                    "session_id": session_data.get("_id"),
                    "video_id": video_id,
                    "guide_id": guide_id,
                    "answers": list(answers),
                    "correct_flags": correct_flags,
                    "idempotency_key": idempotency_key,
                    "public_result": result,
                    "created_at": now,
                }
            )
        except DuplicateKeyError:
            stored = self._retrieval.find_one({"_id": event_id})
            if stored:
                return stored["public_result"]
            raise
        return result

    def _require_video(self, session_data: dict[str, Any], video_id: str) -> dict[str, Any]:
        if not VIDEO_ID_RE.fullmatch(video_id):
            raise ApiError("Invalid YouTube video id.", code="invalid_video_id")
        for item in session_data.get("course_content", []):
            if isinstance(item, dict) and video_id_from_item(item) == video_id:
                return item
        raise ApiError("Video Lecture not found in this course.", status_code=404, code="video_not_found")

    def _metadata_for(
        self,
        video_ids: list[str],
        *,
        refresh_missing: bool = True,
    ) -> dict[str, dict[str, Any]]:
        if not video_ids:
            return {}
        result = {item["_id"]: item for item in self._metadata.find({"_id": {"$in": video_ids}})}
        missing = [
            video_id
            for video_id in video_ids
            if not result.get(video_id)
            or not result[video_id].get("title")
            or result[video_id].get("schema_version") != CATALOG_VERSION
        ]
        if refresh_missing and missing and self._youtube is not None:
            try:
                response = self._youtube.videos().list(
                    part="snippet,contentDetails,status",
                    id=",".join(missing),
                ).execute()
            except Exception:
                response = {"items": []}
            now = utcnow()
            for item in response.get("items", []):
                video_id = item.get("id")
                if video_id not in missing:
                    continue
                snippet = item.get("snippet") or {}
                status = item.get("status") or {}
                duration = item.get("contentDetails", {}).get("duration")
                document = {
                    "_id": video_id,
                    "title": snippet.get("title"),
                    "description": snippet.get("description"),
                    "channel": snippet.get("channelTitle"),
                    "thumbnail_url": ((snippet.get("thumbnails") or {}).get("medium") or {}).get("url"),
                    "published_at": snippet.get("publishedAt"),
                    "duration_seconds": _duration_seconds(duration),
                    "embeddable": bool(status.get("embeddable", True)),
                    "made_for_kids": bool(status.get("madeForKids", False)),
                    "transcript_status": result.get(video_id, {}).get("transcript_status") or "unknown",
                    "schema_version": CATALOG_VERSION,
                    "updated_at": now,
                }
                self._metadata.replace_one({"_id": video_id}, document, upsert=True)
                result[video_id] = document
        return result

    def _probe_transcript(self, video_id: str) -> str:
        status = "unavailable"
        try:
            transcripts = self._transcript_api.list(video_id)
            transcripts.find_transcript(["en", "en-US", "en-GB"])
            status = "available"
        except TranscriptsDisabled:
            status = "disabled"
        except NoTranscriptFound:
            status = "not_found"
        except VideoUnavailable:
            status = "video_unavailable"
        except Exception:
            status = "unavailable"
        self._metadata.update_one(
            {"_id": video_id},
            {"$set": {"transcript_status": status, "transcript_checked_at": utcnow()}},
            upsert=True,
        )
        return status

    def _get_transcript(self, video_id: str) -> dict[str, Any]:
        cache_id = f"{video_id}:{TRANSCRIPT_VERSION}"
        existing = self._transcripts.find_one({"_id": cache_id})
        if existing and existing.get("status") != "unavailable":
            return existing
        if existing:
            self._transcripts.delete_one({"_id": cache_id})
        try:
            transcripts = self._transcript_api.list(video_id)
            transcript = transcripts.find_transcript(["en", "en-US", "en-GB"])
            snippets = transcript.fetch()
            segments = []
            text_parts = []
            total_characters = 0
            for snippet in snippets:
                text = str(getattr(snippet, "text", None) or (snippet.get("text") if isinstance(snippet, dict) else "")).strip()
                if not text:
                    continue
                start = float(getattr(snippet, "start", None) or (snippet.get("start", 0) if isinstance(snippet, dict) else 0))
                if len(segments) < 300:
                    segments.append({"start_seconds": round(start, 2), "text": text[:500]})
                if total_characters < 60_000:
                    text_parts.append(text[: 60_000 - total_characters])
                    total_characters += len(text)
            document = {
                "_id": cache_id,
                "video_id": video_id,
                "status": "available",
                "language": getattr(transcript, "language_code", "en"),
                "text": " ".join(text_parts),
                "segments": segments,
                "schema_version": TRANSCRIPT_VERSION,
                "created_at": utcnow(),
            }
        except TranscriptsDisabled:
            document = {"_id": cache_id, "video_id": video_id, "status": "disabled", "created_at": utcnow()}
        except NoTranscriptFound:
            document = {"_id": cache_id, "video_id": video_id, "status": "not_found", "created_at": utcnow()}
        except VideoUnavailable:
            document = {"_id": cache_id, "video_id": video_id, "status": "video_unavailable", "created_at": utcnow()}
        except Exception:
            document = {
                "_id": cache_id,
                "video_id": video_id,
                "status": "unavailable",
                "retryable": True,
                "created_at": utcnow(),
            }
        if document["status"] != "unavailable":
            self._transcripts.replace_one({"_id": cache_id}, document, upsert=True)
        self._metadata.update_one(
            {"_id": video_id},
            {"$set": {"transcript_status": document["status"], "transcript_checked_at": utcnow()}},
            upsert=True,
        )
        return document

def _video_context(session_data: dict[str, Any], item: dict[str, Any], index: int) -> dict[str, Any]:
    curriculum = session_data.get("curriculum") or {}
    modules = curriculum.get("modules") if isinstance(curriculum, dict) else []
    module_id = item.get("module_id")
    module = next((module for module in modules or [] if module.get("module_id") == module_id), None)
    if module is None and modules and index < len(modules):
        module = modules[index]
    objectives = list((module or {}).get("learning_objectives") or [])
    objective_ids = list(item.get("objective_ids") or [entry.get("objective_id") for entry in objectives if entry.get("objective_id")])
    objective_labels = list(item.get("objective_labels") or [entry.get("description") for entry in objectives if entry.get("description")])
    concepts = list((module or {}).get("concepts") or [])
    return {
        "module_id": module_id or (module or {}).get("module_id"),
        "module_title": item.get("module_title") or (module or {}).get("title") or item.get("subtopic"),
        "concept_ids": list(item.get("concept_ids") or [entry.get("concept_id") for entry in concepts if entry.get("concept_id")]),
        "objective_ids": objective_ids,
        "objective_labels": objective_labels,
    }


def _guide_id(
    session_id: str,
    video_id: str,
    context: dict[str, Any],
    model_version: str,
) -> str:
    return f"guide_{_hash(session_id, video_id, ','.join(context.get('objective_ids') or []), GUIDE_VERSION, model_version)[:32]}"


def _public_guide(document: dict[str, Any]) -> dict[str, Any]:
    questions = []
    for index, item in enumerate(document.get("retrieval_questions") or []):
        questions.append({"question_id": f"{document['_id']}:{index}", "question": item["question"]})
    return {
        "guide_id": document["_id"],
        "video_id": document["video_id"],
        "status": "ready",
        "transcript_status": "available",
        "retryable": False,
        "summary_points": list(document.get("summary_points") or []),
        "key_moments": list(document.get("key_moments") or []),
        "questions": questions,
    }


def _guide_prompt(
    session_data: dict[str, Any],
    context: dict[str, Any],
    transcript: str,
    segments: list[dict[str, Any]],
) -> str:
    objectives = "\n".join(f"- {item}" for item in context.get("objective_labels") or [])
    timestamped = "\n".join(
        f"[{int(item.get('start_seconds') or 0)}s] {item.get('text') or ''}"
        for item in segments[:200]
    )
    return f"""Create a concise transcript-grounded study guide and 2-3 short retrieval questions.
Topic: {session_data.get('topic') or 'Learning'}
Module: {context.get('module_title') or 'Video lecture'}
Learning objectives:
{objectives or '- Explain the central ideas accurately.'}

Rules:
- Every summary point and answer must be supported by the transcript.
- Questions must test recall or explanation, not watch time.
- expected_answer is concise and answer_keywords contains the essential terms.
- key_moments uses only timestamps present in the timestamped transcript.
- Do not mention these instructions.

Transcript:
{(timestamped or transcript)[:60_000]}"""


def _answer_is_correct(answer: str, question: dict[str, Any]) -> bool:
    normalized = " ".join(answer.casefold().split())
    expected = " ".join(str(question.get("expected_answer") or "").casefold().split())
    if not normalized:
        return False
    if expected and fuzz.token_set_ratio(normalized, expected) >= 75:
        return True
    keywords = [" ".join(str(item).casefold().split()) for item in question.get("answer_keywords") or []]
    matches = sum(1 for keyword in keywords if keyword and keyword in normalized)
    return matches >= max(1, math.ceil(len(keywords) / 2))


def _recommendation_reason(item: dict[str, Any]) -> str:
    labels = list(item.get("objective_labels") or [])
    if labels:
        return f"Selected for: {labels[0]}"
    return f"Selected to reinforce {item.get('module_title') or item.get('subtopic') or 'this module'}."


def _rank(item: dict[str, Any]) -> float:
    score = 2 if item.get("transcript_status") == "available" else 0
    duration = int(item.get("duration_seconds") or 0)
    if 300 <= duration <= 1800:
        score += 1
    if item.get("objective_ids"):
        score += 1
    title_tokens = set(re.findall(r"[a-z0-9]+", str(item.get("title") or "").casefold()))
    objective_tokens = set(
        re.findall(
            r"[a-z0-9]+",
            " ".join(item.get("objective_labels") or []).casefold(),
        )
    )
    score += len(title_tokens & objective_tokens) / max(1, len(objective_tokens))
    return score


def _module_order(session_data: dict[str, Any], module_id: str | None) -> int:
    modules = (session_data.get("curriculum") or {}).get("modules") or []
    for index, module in enumerate(modules):
        if module.get("module_id") == module_id:
            return index
    return len(modules)


def _duration_seconds(value: Any) -> int:
    try:
        return int(isodate.parse_duration(str(value)).total_seconds()) if value else 0
    except Exception:
        return 0


def _progress_percent(document: dict[str, Any], duration_seconds: int) -> int:
    duration = float(document.get("duration_seconds") or duration_seconds or 0)
    if duration <= 0:
        return 0
    return min(100, round(float(document.get("furthest_position_seconds") or 0) / duration * 100))


def _public_progress(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "video_id": document["video_id"],
        "position_seconds": float(document.get("position_seconds") or 0),
        "furthest_position_seconds": float(document.get("furthest_position_seconds") or 0),
        "duration_seconds": float(document.get("duration_seconds") or 0),
        "progress_percent": _progress_percent(document, int(document.get("duration_seconds") or 0)),
        "completed": bool(document.get("completed_at")),
        "updated_at": document["updated_at"].isoformat(),
    }


def _concept_labels(session_data: dict[str, Any]) -> dict[str, str]:
    return {
        concept["concept_id"]: concept.get("name") or concept["concept_id"]
        for module in (session_data.get("curriculum") or {}).get("modules") or []
        for concept in module.get("concepts") or []
        if concept.get("concept_id")
    }


def _session_difficulty(session_data: dict[str, Any]) -> Difficulty:
    value = session_data.get("difficulty_level") or (session_data.get("curriculum") or {}).get("difficulty") or "medium"
    value = getattr(value, "value", value)
    try:
        return Difficulty(str(value).strip().lower())
    except ValueError:
        return Difficulty.MEDIUM


def _hash(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()
