from __future__ import annotations

from bson import ObjectId
from flask import jsonify, request, session

from backend.clients import get_vision_client
from backend.extensions import mongo
from backend.lexinit.api.errors import ApiError
from backend.lexinit.api.validation import parse_json_model
from backend.lexinit.schemas import SourceSearchRequest
from backend.lexinit.services.document_learning import DocumentLearningService


def authenticated_user_id() -> str:
    value = session.get("user_id")
    if not isinstance(value, str) or not value:
        raise ApiError("User not logged in.", status_code=401, code="authentication_required")
    try:
        return str(ObjectId(value))
    except Exception as exc:
        session.clear()
        raise ApiError("User not logged in.", status_code=401, code="authentication_required") from exc


def source_service() -> DocumentLearningService:
    return DocumentLearningService(
        source_collection=mongo.db.source_documents,
        file_collection=mongo.db.source_files,
        page_collection=mongo.db.source_pages,
        chunk_collection=mongo.db.source_chunks,
        vision_client_factory=get_vision_client,
    )


def register_routes(app):
    @app.route("/api/v1/sources", methods=["GET"])
    def list_sources():
        user_id = authenticated_user_id()
        items = source_service().list_sources(user_id=user_id)
        return jsonify({"sources": items, "count": len(items)})

    @app.route("/api/v1/sources", methods=["POST"])
    def upload_source():
        user_id = authenticated_user_id()
        file = request.files.get("file")
        if file is None:
            raise ApiError("Choose a PDF or image to upload.", code="source_file_required")
        result, created = source_service().ingest(user_id=user_id, file=file)
        return jsonify({"source": result, "deduplicated": not created}), 201 if created else 200

    @app.route("/api/v1/sources/<source_id>", methods=["GET"])
    def get_source(source_id):
        return jsonify(
            {"source": source_service().get_source(user_id=authenticated_user_id(), source_id=source_id)}
        )

    @app.route("/api/v1/sources/<source_id>", methods=["DELETE"])
    def delete_source(source_id):
        source_service().delete(user_id=authenticated_user_id(), source_id=source_id)
        return jsonify({"success": True})

    @app.route("/api/v1/sources/<source_id>/retry", methods=["POST"])
    def retry_source(source_id):
        result = source_service().retry(user_id=authenticated_user_id(), source_id=source_id)
        return jsonify({"source": result})

    @app.route("/api/v1/sources/<source_id>/pages/<int:page_number>", methods=["GET"])
    def source_page(source_id, page_number):
        return jsonify(
            source_service().page(
                user_id=authenticated_user_id(),
                source_id=source_id,
                page_number=page_number,
            )
        )

    @app.route("/api/v1/sources/search", methods=["POST"])
    def search_sources():
        user_id = authenticated_user_id()
        payload = parse_json_model(
            SourceSearchRequest,
            request.get_json(silent=True),
            field_messages={
                "source_ids": "Choose one to five valid sources.",
                "query": "Enter a search of at least two characters.",
                "limit": "Choose between one and twelve results.",
            },
        )
        results = source_service().retrieve(
            user_id=user_id,
            source_ids=payload.source_ids,
            query=payload.query,
            limit=payload.limit,
        )
        return jsonify({"results": results, "count": len(results)})
