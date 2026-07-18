from __future__ import annotations

import os
import re

from bson import ObjectId
from flask import jsonify, request, session

from backend.clients import get_gemini_model, get_youtube_client
from backend.extensions import mongo
from backend.lexinit.api.errors import ApiError
from backend.lexinit.api.validation import parse_json_model
from backend.lexinit.repositories import MongoAdaptiveLearningRepository
from backend.lexinit.schemas import VideoProgressRequest, VideoRetrievalCheckRequest
from backend.lexinit.services.video_learning import VideoLearningService
from backend.session_store import get_user_session
from backend.validation import valid_safe_id, valid_video_id


IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,160}$")


def _authenticated_user_id() -> str:
    value = session.get("user_id")
    if not isinstance(value, str) or not value:
        raise ApiError(
            "User not logged in.",
            status_code=401,
            code="authentication_required",
        )
    try:
        return str(ObjectId(value))
    except Exception as exc:
        session.clear()
        raise ApiError(
            "User not logged in.",
            status_code=401,
            code="authentication_required",
        ) from exc


def _owned_session(user_id: str, session_id: str):
    if not valid_safe_id(session_id):
        raise ApiError("Invalid course link.", code="invalid_session_id")
    document = get_user_session(user_id, session_id)
    if not document:
        raise ApiError("Course not found.", status_code=404, code="session_not_found")
    return document


def _idempotency_key() -> str:
    value = request.headers.get("Idempotency-Key", "").strip()
    if not IDEMPOTENCY_RE.fullmatch(value):
        raise ApiError(
            "A valid Idempotency-Key header is required.",
            code="invalid_idempotency_key",
        )
    return value


def _service(*, with_model: bool = False) -> VideoLearningService:
    youtube_client = get_youtube_client() if os.environ.get("YOUTUBE_API_KEY") else None
    repository = MongoAdaptiveLearningRepository(
        evidence_collection=mongo.db.mastery_evidence,
        mastery_collection=mongo.db.concept_mastery,
        decisions_collection=mongo.db.adaptation_decisions,
    )
    return VideoLearningService(
        metadata_collection=mongo.db.video_metadata_cache,
        transcript_collection=mongo.db.video_transcript_cache,
        guide_collection=mongo.db.video_study_guides,
        progress_collection=mongo.db.video_progress,
        retrieval_collection=mongo.db.video_retrieval_events,
        adaptive_repository=repository,
        youtube_client=youtube_client,
        model=get_gemini_model() if with_model else None,
    )


def register_routes(app):
    @app.route("/api/v1/sessions/<session_id>/videos")
    def video_catalog(session_id):
        user_id = _authenticated_user_id()
        session_data = _owned_session(user_id, session_id)
        probe = request.args.get("probe_transcripts", "0") == "1"
        hydrate = request.args.get("hydrate_metadata", "0") == "1"
        return jsonify(
            _service().catalog(
                user_id=user_id,
                session_data=session_data,
                probe_transcripts=probe,
                hydrate_metadata=hydrate,
            )
        )

    @app.route("/api/v1/sessions/<session_id>/videos/<video_id>/progress", methods=["PUT"])
    def save_video_progress(session_id, video_id):
        user_id = _authenticated_user_id()
        if not valid_video_id(video_id):
            raise ApiError("Invalid YouTube video id.", code="invalid_video_id")
        payload = parse_json_model(
            VideoProgressRequest,
            request.get_json(silent=True),
            field_messages={
                "position_seconds": "Invalid playback position.",
                "duration_seconds": "Invalid video duration.",
                "state": "Invalid playback state.",
            },
        )
        result = _service().save_progress(
            user_id=user_id,
            session_data=_owned_session(user_id, session_id),
            video_id=video_id,
            position_seconds=payload.position_seconds,
            duration_seconds=payload.duration_seconds,
            state=payload.state,
        )
        return jsonify(result)

    @app.route("/api/v1/sessions/<session_id>/videos/<video_id>/study-guide")
    def video_study_guide(session_id, video_id):
        user_id = _authenticated_user_id()
        if not valid_video_id(video_id):
            raise ApiError("Invalid YouTube video id.", code="invalid_video_id")
        try:
            result = _service(with_model=True).study_guide(
                user_id=user_id,
                session_data=_owned_session(user_id, session_id),
                video_id=video_id,
            )
        except ApiError:
            raise
        except Exception as exc:
            app.logger.exception("video_study_guide_failed video_id=%s", video_id)
            raise ApiError(
                "The Lecture Guide is temporarily unavailable.",
                status_code=503,
                code="video_study_guide_unavailable",
            ) from exc
        return jsonify(result)

    @app.route(
        "/api/v1/sessions/<session_id>/videos/<video_id>/retrieval-check",
        methods=["POST"],
    )
    def submit_video_retrieval_check(session_id, video_id):
        user_id = _authenticated_user_id()
        if not valid_video_id(video_id):
            raise ApiError("Invalid YouTube video id.", code="invalid_video_id")
        payload = parse_json_model(
            VideoRetrievalCheckRequest,
            request.get_json(silent=True),
            field_messages={
                "guide_id": "Invalid Lecture Guide.",
                "answers": "Answer every retrieval question.",
            },
        )
        result = _service().submit_retrieval_check(
            user_id=user_id,
            session_data=_owned_session(user_id, session_id),
            video_id=video_id,
            guide_id=payload.guide_id,
            answers=payload.answers,
            idempotency_key=_idempotency_key(),
        )
        return jsonify(result)
