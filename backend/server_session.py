import secrets
from datetime import datetime, timezone

from flask.sessions import SessionInterface, SessionMixin
from werkzeug.datastructures import CallbackDict


class MongoSession(CallbackDict, SessionMixin):
    def __init__(self, initial=None, sid=None, new=False):
        def on_update(_):
            self.modified = True

        super().__init__(initial or {}, on_update)
        self.sid = sid
        self.new = new
        self.modified = False


class MongoSessionInterface(SessionInterface):
    def __init__(self, mongo_extension, collection_name="server_sessions"):
        self.mongo_extension = mongo_extension
        self.collection_name = collection_name

    @property
    def collection(self):
        return self.mongo_extension.db[self.collection_name]

    def generate_sid(self):
        return secrets.token_urlsafe(32)

    def get_expiration_time(self, app, session):
        if session.permanent:
            return datetime.now(timezone.utc) + app.permanent_session_lifetime
        return None

    def open_session(self, app, request):
        sid = request.cookies.get(self.get_cookie_name(app))
        if not sid:
            return MongoSession(sid=self.generate_sid(), new=True)

        stored = self.collection.find_one({"_id": sid})
        if not stored:
            return MongoSession(sid=self.generate_sid(), new=True)

        expires_at = stored.get("expires_at")
        if expires_at and expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
            self.collection.delete_one({"_id": sid})
            return MongoSession(sid=self.generate_sid(), new=True)

        return MongoSession(initial=stored.get("data", {}), sid=sid)

    def save_session(self, app, session, response):
        cookie_name = self.get_cookie_name(app)
        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)
        secure = self.get_cookie_secure(app)
        samesite = self.get_cookie_samesite(app)
        httponly = self.get_cookie_httponly(app)

        if not session:
            if session.modified:
                self.collection.delete_one({"_id": session.sid})
                response.delete_cookie(
                    cookie_name,
                    domain=domain,
                    path=path,
                    secure=secure,
                    samesite=samesite,
                    httponly=httponly,
                )
            return

        expires_at = self.get_expiration_time(app, session)
        self.collection.update_one(
            {"_id": session.sid},
            {
                "$set": {
                    "data": dict(session),
                    "expires_at": expires_at,
                    "updated_at": datetime.now(timezone.utc),
                },
                "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
        response.set_cookie(
            cookie_name,
            session.sid,
            expires=expires_at,
            httponly=httponly,
            domain=domain,
            path=path,
            secure=secure,
            samesite=samesite,
        )
