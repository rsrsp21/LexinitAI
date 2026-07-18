from flask import current_app, jsonify, redirect, send_from_directory, session, url_for


def register_routes(app):
    def react_index():
        frontend_dist = current_app.config["FRONTEND_DIST"]
        index_path = frontend_dist / "index.html"
        if index_path.exists():
            return send_from_directory(frontend_dist, "index.html")
        return None

    @app.route("/", methods=["GET"])
    def home():
        react_response = react_index()
        if react_response:
            return react_response
        return jsonify(
            {
                "message": "React build not found. Run `npm run dev` in frontend for development, or `npm run build` to let Flask serve the React app."
            }
        ), 503

    @app.route("/assets/<path:filename>")
    def frontend_assets(filename):
        return send_from_directory(current_app.config["FRONTEND_DIST"] / "assets", filename)

    @app.route("/images/<path:filename>")
    def frontend_images(filename):
        dist_images = current_app.config["FRONTEND_DIST"] / "images"
        if (dist_images / filename).exists():
            return send_from_directory(dist_images, filename)
        return send_from_directory(current_app.config["FRONTEND_PUBLIC"] / "images", filename)

    @app.route("/docs/<path:filename>")
    def frontend_docs(filename):
        dist_docs = current_app.config["FRONTEND_DIST"] / "docs"
        if (dist_docs / filename).exists():
            return send_from_directory(dist_docs, filename)
        return send_from_directory(current_app.config["FRONTEND_PUBLIC"] / "docs", filename)

    @app.route("/dashboard")
    @app.route("/account")
    @app.route("/performance")
    @app.route("/terms")
    @app.route("/privacy")
    @app.route("/sessions/<path:unused>")
    @app.route("/user/<path:unused>")
    def frontend_app(unused=None):
        react_response = react_index()
        if react_response:
            return react_response
        return redirect(url_for("home"))

    @app.route("/logout")
    def logout():
        session.clear()
        response = redirect(url_for("home"))
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response
