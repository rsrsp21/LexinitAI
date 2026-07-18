from __future__ import annotations

import hmac

from flask import current_app, jsonify, request

from backend.extensions import mongo
from backend.lexinit.observability import evaluate_api_alerts, metrics_snapshot


def _has_metrics_access() -> bool:
    expected = current_app.config.get("METRICS_TOKEN")
    supplied = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return bool(expected and supplied and hmac.compare_digest(str(expected), supplied))


def register_routes(app):
    @app.route("/api/v1/health/live")
    def health_live():
        return jsonify({"status": "ok"})

    @app.route("/api/v1/health/ready")
    def health_ready():
        try:
            mongo.db.command("ping")
        except Exception:
            return jsonify({"status": "not_ready", "database": "unavailable"}), 503
        required = {
            "secret_key": bool(current_app.config.get("SECRET_KEY")),
            "gemini": bool(current_app.config.get("GEMINI_API_KEY")),
            "youtube": bool(current_app.config.get("YOUTUBE_API_KEY")),
        }
        status = "ready" if all(required.values()) else "degraded"
        return jsonify({"status": status, "database": "ready", "services": required}), 200

    @app.route("/api/v1/health/metrics")
    def health_metrics():
        if not _has_metrics_access():
            return jsonify({"message": "Not found."}), 404
        return jsonify(metrics_snapshot())

    @app.route("/api/v1/health/alerts")
    def health_alerts():
        if not _has_metrics_access():
            return jsonify({"message": "Not found."}), 404
        try:
            mongo.db.command("ping")
            database_ready = True
        except Exception:
            database_ready = False
        result = evaluate_api_alerts(current_app.config, database_ready=database_ready)
        if result["alerts"]:
            current_app.logger.warning(
                "active_alerts ids=%s", ",".join(alert["id"] for alert in result["alerts"])
            )
        return jsonify(result), 503 if result["alerts"] else 200
