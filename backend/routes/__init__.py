from .activity import register_routes as register_activity_routes
from .adaptive import register_routes as register_adaptive_routes
from .api import register_routes as register_api_routes
from .auth import register_routes as register_auth_routes
from .content import register_routes as register_content_routes
from .core import register_routes as register_core_routes
from .uploads import register_routes as register_upload_routes
from .learning_loop import register_routes as register_learning_loop_routes
from .video_learning import register_routes as register_video_learning_routes
from .sources import register_routes as register_source_routes
from .security import register_routes as register_security_routes
from .health import register_routes as register_health_routes
from .course import register_routes as register_course_routes


def register_routes(app):
    register_core_routes(app)
    register_auth_routes(app)
    register_activity_routes(app)
    register_adaptive_routes(app)
    register_learning_loop_routes(app)
    register_video_learning_routes(app)
    register_source_routes(app)
    register_security_routes(app)
    register_health_routes(app)
    register_course_routes(app)
    register_upload_routes(app)
    register_content_routes(app)
    register_api_routes(app)
