from __future__ import annotations

import collections
import hmac
import logging
import secrets
import threading
import time
import uuid

from flask import current_app, request, session

from backend.lexinit.api.errors import ApiError


logger = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
RATE_LIMIT_EXEMPT_PATHS = {
    "/api/v1/health/live",
    "/api/v1/health/ready",
}

# Authentication endpoints live outside /api/ but must be throttled: they are
# targets for password guessing, code guessing and email flooding. Each entry
# maps a path to (bucket, config key, default limit, window seconds).
_AUTH_LOGIN = ("auth-login", "LOGIN_RATE_LIMIT", 10, 15 * 60)
_AUTH_SEND_CODE = ("auth-send-code", "AUTH_CODE_SEND_RATE_LIMIT", 5, 60 * 60)
_AUTH_VERIFY = ("auth-verify", "AUTH_CODE_VERIFY_RATE_LIMIT", 10, 15 * 60)
AUTH_RATE_POLICIES = {
    "/login": _AUTH_LOGIN,
    "/auth/signup/start": _AUTH_SEND_CODE,
    "/send-code": _AUTH_SEND_CODE,
    "/forgot_password": _AUTH_SEND_CODE,
    "/api/v1/forgot-password": _AUTH_SEND_CODE,
    "/api/forgot-password": _AUTH_SEND_CODE,
    "/api/v1/account/password/start": _AUTH_SEND_CODE,
    "/auth/signup/verify": _AUTH_VERIFY,
    "/auth/signup/profile": _AUTH_VERIFY,
    "/auth/signup/complete": _AUTH_VERIFY,
    "/verify-code": _AUTH_VERIFY,
    "/api/v1/forgot-password/verify": _AUTH_VERIFY,
    "/api/forgot-password/verify": _AUTH_VERIFY,
    "/api/v1/forgot-password/complete": _AUTH_VERIFY,
    "/api/forgot-password/complete": _AUTH_VERIFY,
    "/api/v1/account/password/verify": _AUTH_VERIFY,
    "/api/v1/account/password/complete": _AUTH_VERIFY,
}


class SlidingWindowRateLimiter:
    """In-process limiter. Correct for a single process only."""

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


# Sliding window over a sorted set, done atomically inside Redis so every
# worker process and server shares the same counts.
_REDIS_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
if redis.call('ZCARD', key) >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local retry = math.ceil(window - (now - tonumber(oldest[2])))
  if retry < 1 then retry = 1 end
  return retry
end
redis.call('ZADD', key, now, ARGV[4])
redis.call('EXPIRE', key, math.ceil(window))
return 0
"""


class RedisRateLimiter:
    """Shared limiter backed by Redis; falls back to in-process counting if
    Redis is unreachable so an outage does not take the API down."""

    def __init__(self, redis_client, *, prefix: str = "lexinit:ratelimit:") -> None:
        self._redis = redis_client
        self._script = redis_client.register_script(_REDIS_SLIDING_WINDOW)
        self._prefix = prefix
        self._fallback = SlidingWindowRateLimiter()

    def check(self, key: str, *, limit: int, window_seconds: int, now: float | None = None) -> int:
        try:
            result = self._script(
                keys=[f"{self._prefix}{key}"],
                args=[now if now is not None else time.time(), window_seconds, limit, uuid.uuid4().hex],
            )
            return int(result or 0)
        except Exception:
            logger.warning("rate_limiter_redis_unavailable; using in-process limiter", exc_info=True)
            return self._fallback.check(key, limit=limit, window_seconds=window_seconds, now=now)


def build_rate_limiter(app):
    redis_url = app.config.get("REDIS_URL")
    if redis_url:
        try:
            from redis import Redis

            return RedisRateLimiter(Redis.from_url(redis_url, socket_timeout=0.5, socket_connect_timeout=0.5))
        except Exception:
            logger.warning("rate_limiter_redis_init_failed; using in-process limiter", exc_info=True)
    return SlidingWindowRateLimiter()


def enforce_rate_limit(bucket: str, identity: str, *, limit: int, window_seconds: int) -> None:
    """Apply an extra limit keyed on something other than the client, such as
    the email address being logged into. Raises 429 when exceeded."""
    if current_app.config.get("TESTING"):
        return
    limiter = current_app.extensions["lexinit_rate_limiter"]
    retry_after = limiter.check(f"{bucket}:{identity}", limit=limit, window_seconds=window_seconds)
    if retry_after:
        raise _rate_limited(retry_after)


def _rate_limited(retry_after: int) -> ApiError:
    return ApiError(
        "Too many requests. Please wait and try again.",
        status_code=429,
        code="rate_limit_exceeded",
        details={"retry_after_seconds": retry_after},
    )


def csrf_token() -> str:
    value = session.get("_csrf_token")
    if not isinstance(value, str) or len(value) < 32:
        value = secrets.token_urlsafe(32)
        session["_csrf_token"] = value
    return value


def register_security(app) -> None:
    trusted_proxies = int(app.config.get("TRUSTED_PROXY_COUNT") or 0)
    if trusted_proxies > 0:
        # Behind a reverse proxy, take the client address from X-Forwarded-For
        # so each visitor gets their own limit instead of sharing the proxy's.
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=trusted_proxies,
            x_proto=trusted_proxies,
            x_host=trusted_proxies,
        )

    limiter = build_rate_limiter(app)
    app.extensions["lexinit_rate_limiter"] = limiter

    @app.before_request
    def enforce_request_security():
        if app.config.get("TESTING"):
            return None

        auth_policy = AUTH_RATE_POLICIES.get(request.path) if request.method == "POST" else None
        if auth_policy:
            bucket, config_key, default, window = auth_policy
            # Always keyed on the client address: these requests come before
            # (or instead of) a signed-in session.
            identity = str(request.remote_addr or "anonymous")
            retry_after = limiter.check(
                f"{identity}:{bucket}",
                limit=int(app.config.get(config_key, default)),
                window_seconds=window,
            )
            if retry_after:
                raise _rate_limited(retry_after)
        elif (
            request.path.startswith("/api/") or _starts_generation(request.path)
        ) and request.path not in RATE_LIMIT_EXEMPT_PATHS:
            identity = str(session.get("user_id") or request.remote_addr or "anonymous")
            limit, window = _rate_policy(app, request.path, request.method)
            retry_after = limiter.check(
                f"{identity}:{request.method}:{_rate_bucket(request.path)}",
                limit=limit,
                window_seconds=window,
            )
            if retry_after:
                raise _rate_limited(retry_after)

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
    if method == "POST" and _starts_generation(path):
        return int(app.config.get("GENERATION_START_RATE_LIMIT", 10)), 60 * 60
    if method == "POST" and path == "/api/v1/waitlist":
        return int(app.config.get("WAITLIST_RATE_LIMIT", 10)), 60 * 60
    if method == "POST" and _is_coach_generation(path):
        return int(app.config.get("COACH_RATE_LIMIT", 60)), 60 * 60
    return int(app.config.get("API_RATE_LIMIT_PER_MINUTE", 240)), 60


def _rate_bucket(path: str) -> str:
    if path.startswith("/api/v1/sources"):
        return "sources"
    if path.startswith("/api/v1/generation-runs") or _starts_generation(path):
        return "generation"
    if path == "/api/v1/waitlist":
        return "waitlist"
    if _is_coach_generation(path):
        return "coach"
    if "assessment" in path or "retrieval-check" in path:
        return "assessment"
    return "general"


def _is_coach_generation(path: str) -> bool:
    """Coach calls that run the AI model (answering a check does not)."""
    return path in {
        "/api/v1/coach/fix-it",
        "/api/v1/coach/explain",
        "/api/v1/coach/practice",
        "/api/v1/coach/daily-mix",
    } or (
        path.startswith("/api/v1/sessions/") and path.endswith("/final-assessment")
    ) or (path.startswith("/api/v1/coach/sessions/") and path.endswith("/pre-check"))


def _starts_generation(path: str) -> bool:
    """New generation, regeneration and retry all spend AI calls, so they
    share one start limit."""
    if path in {"/api/v1/generation-runs", "/submit-topic"}:
        return True
    if path.endswith("/retry"):
        return path.startswith(("/api/v1/generation-runs/", "/api/generation-jobs/"))
    if path.endswith("/regenerate"):
        return path.startswith(("/api/v1/sessions/", "/api/sessions/"))
    return False
