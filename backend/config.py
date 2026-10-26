import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_ROOT / ".env", override=False)


def _mongo_uri_with_defaults(uri):
    if not uri:
        return uri

    parsed = urlsplit(uri)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault(
        "serverSelectionTimeoutMS",
        os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", "8000"),
    )
    return urlunsplit(parsed._replace(query=urlencode(query)))


def _env_bool(name, default="false"):
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _selected_mongo_uri():
    if _env_bool("USE_LOCAL_MONGO"):
        return os.environ.get("LOCAL_MONGO_URI", "mongodb://localhost:27017/lexinit")
    return os.environ.get("MONGO_URI")


def _mongo_dns_nameservers():
    if _env_bool("USE_LOCAL_MONGO"):
        return []

    return [
        nameserver.strip()
        for nameserver in os.environ.get("MONGO_DNS_NAMESERVERS", "").split(",")
        if nameserver.strip()
    ]


class Config:
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH", 12 * 1024 * 1024))
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
    USE_LOCAL_MONGO = _env_bool("USE_LOCAL_MONGO")
    LOCAL_MONGO_URI = os.environ.get("LOCAL_MONGO_URI", "mongodb://localhost:27017/lexinit")
    MONGO_URI = _mongo_uri_with_defaults(_selected_mongo_uri())
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "lexinit")
    MONGO_DNS_NAMESERVERS = _mongo_dns_nameservers()
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "lexinit_session")
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    SESSION_REFRESH_EACH_REQUEST = os.environ.get("SESSION_REFRESH_EACH_REQUEST", "true").lower() == "true"
    SERVER_SESSION_COLLECTION = os.environ.get("SERVER_SESSION_COLLECTION", "server_sessions")
    REDIS_URL = os.environ.get("REDIS_URL")
    GENERATION_WORKER_MODE = os.environ.get("GENERATION_WORKER_MODE", "auto")
    GENERATION_QUEUE_NAME = os.environ.get("GENERATION_QUEUE_NAME", "generation")
    GENERATION_LEASE_SECONDS = int(os.environ.get("GENERATION_LEASE_SECONDS", 900))
    GENERATION_RESUME_ON_STARTUP = _env_bool("GENERATION_RESUME_ON_STARTUP", "true")
    CSRF_ENABLED = _env_bool("CSRF_ENABLED", "true")
    API_RATE_LIMIT_PER_MINUTE = int(os.environ.get("API_RATE_LIMIT_PER_MINUTE", 240))
    SOURCE_UPLOAD_RATE_LIMIT = int(os.environ.get("SOURCE_UPLOAD_RATE_LIMIT", 15))
    GENERATION_START_RATE_LIMIT = int(os.environ.get("GENERATION_START_RATE_LIMIT", 10))
    WAITLIST_RATE_LIMIT = int(os.environ.get("WAITLIST_RATE_LIMIT", 10))
    METRICS_TOKEN = os.environ.get("METRICS_TOKEN")
    OTEL_EXPORTER_OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    ALERT_WINDOW_SECONDS = int(os.environ.get("ALERT_WINDOW_SECONDS", 300))
    ALERT_MIN_REQUESTS = int(os.environ.get("ALERT_MIN_REQUESTS", 20))
    ALERT_ERROR_RATE_PERCENT = float(os.environ.get("ALERT_ERROR_RATE_PERCENT", 2))
    ALERT_P95_DURATION_MS = float(os.environ.get("ALERT_P95_DURATION_MS", 2000))

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", 587))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME", "lexinit.inc@gmail.com")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_SUPPRESS_SEND = os.environ.get("MAIL_SUPPRESS_SEND", "false").lower() == "true"
    SIGNUP_OTP_TTL_SECONDS = int(os.environ.get("SIGNUP_OTP_TTL_SECONDS", 300))
    SIGNUP_RESEND_COOLDOWN_SECONDS = int(os.environ.get("SIGNUP_RESEND_COOLDOWN_SECONDS", 30))
    SIGNUP_DRAFT_TTL_SECONDS = int(os.environ.get("SIGNUP_DRAFT_TTL_SECONDS", 900))
    SIGNUP_MAX_CODE_ATTEMPTS = int(os.environ.get("SIGNUP_MAX_CODE_ATTEMPTS", 5))
    PASSWORD_RESET_OTP_TTL_SECONDS = int(os.environ.get("PASSWORD_RESET_OTP_TTL_SECONDS", 300))
    PASSWORD_RESET_RESEND_COOLDOWN_SECONDS = int(os.environ.get("PASSWORD_RESET_RESEND_COOLDOWN_SECONDS", 30))
    PASSWORD_RESET_MAX_CODE_ATTEMPTS = int(os.environ.get("PASSWORD_RESET_MAX_CODE_ATTEMPTS", 5))

    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
    YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
    CLOUD_VISION_API_KEY = os.environ.get("CLOUD_VISION_API_KEY")
    CUSTOM_SEARCH_API = os.environ.get("CUSTOM_SEARCH_API")
    SEARCH_ID = os.environ.get("SEARCH_ID")
    GOOGLE_CREDENTIALS_BASE64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64")

    GEMINI_MODEL_NAME = os.environ.get("GEMINI_MODEL_NAME", "gemini-2.5-flash-lite")
    GEMINI_DEEP_FOCUS_MODEL_NAME = os.environ.get("GEMINI_DEEP_FOCUS_MODEL_NAME", "gemini-2.5-pro")

    CORS_ORIGINS = [
        origin.strip()
        for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if origin.strip()
    ]
