from __future__ import annotations

import collections
import hmac
import secrets
import threading
import time

from flask import request, session

from backend.lexinit.api.errors import ApiError


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
RATE_LIMIT_EXEMPT_PATHS = {
    "/api/v1/health/live",
    "/api/v1/health/ready",
}


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, collections.deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, *, limit: int, window_seconds: int, now: float | None = None) -> int:
        current = now if now is not None else time.monotonic()
        cutoff = current - window_seconds
        with self._lock:
            events = self._events.setdefault(key, collections.deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return max(1, int(window_seconds - (current - events[0])))
            events.append(current)
            if len(self._events) > 10_000:
                self._events = {name: values for name, values in self._events.items() if values}
        return 0


def csrf_token() -> str:
    value = session.get("_csrf_token")
    if not isinstance(value, str) or len(value) < 32:
        value = secrets.token_urlsafe(32)
        session["_csrf_token"] = value
    return value


def register_security(app) -> None:
    limiter = SlidingWindowRateLimiter()
    app.extensions["lexinit_rate_limiter"] = limiter

    @app.before_request
    def enforce_request_security():
        if app.config.get("TESTING"):
            return None

        if request.path.startswith("/api/") and request.path not in RATE_LIMIT_EXEMPT_PATHS:
            identity = str(session.get("user_id") or request.remote_addr or "anonymous")
            limit, window = _rate_policy(app, request.path, request.method)
            retry_after = limiter.check(
                f"{identity}:{request.method}:{_rate_bucket(request.path)}",
                limit=limit,
                window_seconds=window,
            )
            if retry_after:
                raise ApiError(
                    "Too many requests. Please wait and try again.",
                    status_code=429,
                    code="rate_limit_exceeded",
                    details={"retry_after_seconds": retry_after},
                )

        if (
            app.config.get("CSRF_ENABLED", True)
            and request.method not in SAFE_METHODS
            and session.get("user_id")
        ):
            expected = session.get("_csrf_token")
            supplied = request.headers.get("X-CSRF-Token", "")
            if not isinstance(expected, str) or not hmac.compare_digest(expected, supplied):
                raise ApiError(
                    "Your security token expired. Refresh and try again.",
                    status_code=403,
                    code="csrf_token_invalid",
                )
        return None

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
        if request.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        if not app.debug:
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; "
                "base-uri 'self'; object-src 'none'; frame-ancestors 'self'; "
                "script-src 'self' https://www.youtube.com https://s.ytimg.com; "
                "frame-src https://www.youtube.com https://www.youtube-nocookie.com; "
                "connect-src 'self' https://www.youtube.com; "
                "img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; "
                "font-src 'self' data:; media-src 'self' blob:;",
            )
        return response


def _rate_policy(app, path: str, method: str) -> tuple[int, int]:
    if method == "POST" and path == "/api/v1/sources":
        return int(app.config.get("SOURCE_UPLOAD_RATE_LIMIT", 15)), 15 * 60
    if method == "POST" and path == "/api/v1/generation-runs":
        return int(app.config.get("GENERATION_START_RATE_LIMIT", 10)), 60 * 60
    return int(app.config.get("API_RATE_LIMIT_PER_MINUTE", 240)), 60


def _rate_bucket(path: str) -> str:
    if path.startswith("/api/v1/sources"):
        return "sources"
    if path.startswith("/api/v1/generation-runs"):
        return "generation"
    if "assessment" in path or "retrieval-check" in path:
        return "assessment"
    return "general"
