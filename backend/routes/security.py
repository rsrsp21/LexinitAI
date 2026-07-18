from flask import jsonify

from backend.lexinit.security import csrf_token


def register_routes(app):
    @app.route("/api/v1/security/csrf")
    def security_csrf():
        return jsonify({"csrf_token": csrf_token()})
