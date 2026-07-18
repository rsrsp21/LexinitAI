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

    if resume_generation_runs and app.config.get("GENERATION_RESUME_ON_STARTUP"):
        from .services.generation_jobs import resume_incomplete_generation_jobs

        with app.app_context():
            resume_incomplete_generation_jobs(app)

    return app
