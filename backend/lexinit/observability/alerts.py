from __future__ import annotations

import math

from .request_context import recent_request_snapshot


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil((percentile / 100) * len(ordered)) - 1))
    return round(ordered[index], 2)


def evaluate_api_alerts(config, *, database_ready: bool) -> dict:
    window_seconds = int(config.get("ALERT_WINDOW_SECONDS", 300))
    minimum_requests = int(config.get("ALERT_MIN_REQUESTS", 20))
    events = recent_request_snapshot(window_seconds)
    total = len(events)
    failures = sum(1 for event in events if event["status_code"] >= 500)
    error_rate = round((failures / total) * 100, 2) if total else 0.0
    p95_ms = _percentile([event["duration_ms"] for event in events], 95)
    alerts = []

    if not database_ready:
        alerts.append(
            {
                "id": "database_unavailable",
                "severity": "critical",
                "message": "Database readiness check failed.",
            }
        )
    if total >= minimum_requests and error_rate > float(config.get("ALERT_ERROR_RATE_PERCENT", 2)):
        alerts.append(
            {
                "id": "api_error_rate_high",
                "severity": "critical",
                "message": "API server error rate exceeded its configured threshold.",
            }
        )
    if total >= minimum_requests and p95_ms > float(config.get("ALERT_P95_DURATION_MS", 2000)):
        alerts.append(
            {
                "id": "api_latency_high",
                "severity": "warning",
                "message": "API p95 response time exceeded its configured threshold.",
            }
        )

    return {
        "status": "alerting" if alerts else "healthy",
        "window_seconds": window_seconds,
        "sample_size": total,
        "measurements": {"server_error_rate_percent": error_rate, "p95_duration_ms": p95_ms},
        "thresholds": {
            "minimum_requests": minimum_requests,
            "server_error_rate_percent": float(config.get("ALERT_ERROR_RATE_PERCENT", 2)),
            "p95_duration_ms": float(config.get("ALERT_P95_DURATION_MS", 2000)),
        },
        "alerts": alerts,
    }
