from __future__ import annotations

import re
import threading
import time
import uuid
from collections import defaultdict, deque

from flask import g, request


REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_metrics_lock = threading.Lock()
_request_counts = defaultdict(int)
_request_duration_ms = defaultdict(float)
_recent_requests = deque(maxlen=50_000)


def _request_id_from_header() -> str:
    candidate = request.headers.get("X-Request-ID", "").strip()
    if REQUEST_ID_RE.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


def register_request_context(app) -> None:
    @app.before_request
    def begin_request_context() -> None:
        g.request_id = _request_id_from_header()
        g.request_started_at = time.perf_counter()

    @app.after_request
    def complete_request_context(response):
        response.headers["X-Request-ID"] = g.get("request_id", uuid.uuid4().hex)
        elapsed_ms = round((time.perf_counter() - g.get("request_started_at", time.perf_counter())) * 1000, 2)
        route = request.url_rule.rule if request.url_rule else "unmatched"
        metric_key = (request.method, route, f"{response.status_code // 100}xx")
        with _metrics_lock:
            _request_counts[metric_key] += 1
            _request_duration_ms[metric_key] += elapsed_ms
            _recent_requests.append(
                {
                    "recorded_at": time.time(),
                    "duration_ms": elapsed_ms,
                    "status_code": response.status_code,
                    "method": request.method,
                    "route": route,
                }
            )
        app.logger.info(
            "request_complete request_id=%s method=%s path=%s status=%s duration_ms=%s",
            g.get("request_id"),
            request.method,
            request.path,
            response.status_code,
            elapsed_ms,
        )
        return response


def metrics_snapshot() -> dict:
    with _metrics_lock:
        rows = []
        for key, count in sorted(_request_counts.items()):
            method, route, status_group = key
            total_ms = _request_duration_ms[key]
            rows.append(
                {
                    "method": method,
                    "route": route,
                    "status_group": status_group,
                    "count": count,
                    "average_duration_ms": round(total_ms / count, 2) if count else 0,
                }
            )
        return {"requests": rows}


def recent_request_snapshot(window_seconds: int = 300, *, now: float | None = None) -> list[dict]:
    cutoff = (time.time() if now is None else now) - window_seconds
    with _metrics_lock:
        while _recent_requests and _recent_requests[0]["recorded_at"] < cutoff:
            _recent_requests.popleft()
        return [dict(row) for row in _recent_requests]
