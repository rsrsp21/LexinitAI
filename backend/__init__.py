from pathlib import Path

from flask import Flask

from .config import Config
from .db import ensure_database_schema
from .errors import register_error_handlers
from .extensions import init_extensions
from .lexinit.observability import configure_telemetry, register_request_context
from .lexinit.security import register_security
from .routes import register_routes


def create_app(*, resume_generation_runs=True):
    project_root = Path(__file__).resolve().parent.parent

    app = Flask(__name__)
    app.config.from_object(Config)
    app.config["FRONTEND_DIST"] = project_root / "frontend" / "dist"
    app.config["FRONTEND_PUBLIC"] = project_root / "frontend" / "public"

    init_extensions(app)
    register_request_context(app)
    configure_telemetry(app)
    register_security(app)
    ensure_database_schema(app)
    register_error_handlers(app)
    register_routes(app)
    _run_data_backfills(app)

    if resume_generation_runs and app.config.get("GENERATION_RESUME_ON_STARTUP"):
        from .services.generation_jobs import resume_incomplete_generation_jobs

        with app.app_context():
            resume_incomplete_generation_jobs(app)

    return app


def _run_data_backfills(app):
    """Small idempotent data fixes that must run before related records expire."""
    try:
        from .extensions import mongo
        from .lexinit.services.concept_coach import backfill_submission_refs

        from .lexinit.services.learner_model import backfill_concept_labels

        with app.app_context():
            backfill_submission_refs(mongo.db)
            backfill_concept_labels(mongo.db)
    except Exception:
        app.logger.warning("data_backfill_failed", exc_info=True)
