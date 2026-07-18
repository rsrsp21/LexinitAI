from flask_cors import CORS
from flask_mail import Mail

from .db import LazyMongo
from .server_session import MongoSessionInterface


mongo = LazyMongo()
mail = Mail()
cors = CORS()


def init_extensions(app):
    mongo.init_app(app)
    app.session_interface = MongoSessionInterface(
        mongo,
        app.config.get("SERVER_SESSION_COLLECTION", "server_sessions"),
    )
    mail.init_app(app)
    cors.init_app(
        app,
        resources={r"/*": {"origins": app.config["CORS_ORIGINS"]}},
        supports_credentials=True,
    )
