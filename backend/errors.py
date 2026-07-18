from flask import g, jsonify, request
from pymongo.errors import PyMongoError, ServerSelectionTimeoutError
from werkzeug.exceptions import HTTPException

from backend.lexinit.api.errors import ApiError


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(exc):
        payload = {
            "success": False,
            "message": exc.message,
            "error": {
                "code": exc.code,
                "request_id": g.get("request_id"),
            },
        }
        if exc.details:
            payload["error"]["details"] = exc.details
        return jsonify(payload), exc.status_code

    @app.errorhandler(ServerSelectionTimeoutError)
    def handle_server_selection_timeout(exc):
        app.logger.error("database_connection_error request_id=%s error=%s", g.get("request_id"), exc)
        return jsonify(
            {
                "success": False,
                "message": (
                    "Your saved learning data is temporarily unavailable. Please try again shortly."
                ),
            }
        ), 503

    @app.errorhandler(PyMongoError)
    def handle_pymongo_error(exc):
        app.logger.error("database_error request_id=%s error=%s", g.get("request_id"), exc)
        return jsonify(
            {
                "success": False,
                "message": "Your saved learning data is temporarily unavailable. Please try again shortly.",
            }
        ), 503

    @app.errorhandler(Exception)
    def handle_unexpected_error(exc):
        if isinstance(exc, HTTPException):
            if request.path.startswith("/api/"):
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": exc.description or "Request failed.",
                            "error": {
                                "code": f"http_{exc.code or 500}",
                                "request_id": g.get("request_id"),
                            },
                        }
                    ),
                    exc.code or 500,
                )
            return exc
        app.logger.exception(
            "unexpected_error request_id=%s method=%s path=%s",
            g.get("request_id"),
            request.method,
            request.path,
        )
        if request.path.startswith("/api/") or request.is_json:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Something went wrong. Please try again.",
                        "error": {
                            "code": "internal_error",
                            "request_id": g.get("request_id"),
                        },
                    }
                ),
                500,
            )
        raise exc
