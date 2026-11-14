"""Plan quotas and request rate limits against a real database."""

import datetime
import threading

from bson import ObjectId

from backend.services.generation_quota import consume_generation_quota, release_quota_charge


def make_user(db, plan="free", **extra):
    document = {
        "_id": ObjectId(),
        "email": f"{ObjectId()}@example.test",
        "password": "x" * 40,
        "verified": True,
        "plan": plan,
        "rate_limit": 0,
        "deep_rate_limit": 0,
        **extra,
    }
    db.users.insert_one(document)
    return document["_id"]


def counters(db, user_id):
    document = db.users.find_one({"_id": user_id})
    return document.get("rate_limit"), document.get("deep_rate_limit")


def allowed(app, user_id, plan, mode, attempts):
    with app.test_request_context():
        return sum(
            consume_generation_quota(str(user_id), {"plan": plan}, mode)[0] is None
            for _ in range(attempts)
        )


def test_each_plan_is_capped_per_mode(app, db):
    assert allowed(app, make_user(db, "free"), "free", "Basic", 7) == 5
    assert allowed(app, make_user(db, "free"), "free", "Pro Reasoning", 5) == 3
    assert allowed(app, make_user(db, "plus"), "plus", "Basic", 22) == 20
    assert allowed(app, make_user(db, "plus"), "plus", "Pro Reasoning", 12) == 10
    assert allowed(app, make_user(db, "pro"), "pro", "Pro Reasoning", 32) == 30


def test_quick_and_deep_focus_have_separate_budgets(app, db):
    user_id = make_user(db)
    assert allowed(app, user_id, "free", "Basic", 5) == 5
    assert allowed(app, user_id, "free", "Pro Reasoning", 3) == 3
    assert counters(db, user_id) == (5, 3)


def run_concurrently(app, user_id, count):
    results = []

    def worker():
        with app.test_request_context():
            results.append(consume_generation_quota(str(user_id), {"plan": "free"}, "Basic")[0] is None)

    threads = [threading.Thread(target=worker) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sum(results)


def test_concurrent_requests_cannot_exceed_the_limit(app, db):
    user_id = make_user(db)
    assert run_concurrently(app, user_id, 20) == 5
    assert counters(db, user_id) == (5, 0)


def test_only_one_request_opens_a_new_window(app, db):
    expired = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)
    user_id = make_user(db, first_submission_time=expired, rate_limit=5)
    assert run_concurrently(app, user_id, 12) == 5
    assert counters(db, user_id) == (5, 0)


def test_a_refund_returns_the_slot_within_its_window_only(app, db):
    user_id = make_user(db)
    with app.test_request_context():
        _, charge = consume_generation_quota(str(user_id), {"plan": "free"}, "Basic")
        release_quota_charge(user_id, charge)
        assert counters(db, user_id) == (0, 0)

        _, old_charge = consume_generation_quota(str(user_id), {"plan": "free"}, "Basic")
        db.users.update_one(
            {"_id": user_id},
            {"$set": {"first_submission_time": datetime.datetime.now(datetime.timezone.utc), "rate_limit": 1}},
        )
        release_quota_charge(user_id, old_charge)  # belongs to the previous window
        assert counters(db, user_id) == (1, 0)


def test_the_limit_message_says_when_to_come_back(app, db):
    now = datetime.datetime.now(datetime.timezone.utc)
    user_id = make_user(db, first_submission_time=now, rate_limit=5)
    with app.test_request_context():
        response, charge = consume_generation_quota(str(user_id), {"plan": "free"}, "Basic")
    assert charge is None and response[1] == 429
    assert "5 per 24 hours" in response[0].get_json()["message"]


def post_login(app, email, address):
    return app.test_client().post(
        "/login",
        data={"login-email": email, "login-password": "wrong-password"},
        environ_base={"REMOTE_ADDR": address},
    )


def test_login_is_limited_per_address(app):
    codes = [post_login(app, "nobody@example.test", "10.1.1.1").status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_login_is_limited_per_email_across_addresses(app):
    codes = [post_login(app, "target@example.test", f"10.2.2.{index}").status_code for index in range(11)]
    assert codes[10] == 429
    body = post_login(app, "target@example.test", "10.2.3.1").get_json()
    assert body["error"]["code"] == "rate_limit_exceeded"
    assert body["error"]["details"]["retry_after_seconds"] > 0


def test_sending_codes_is_limited(app):
    web = app.test_client()
    codes = [
        web.post("/send-code", data={"signup-email": "a@example.test"}, environ_base={"REMOTE_ADDR": "10.3.3.3"}).status_code
        for _ in range(6)
    ]
    assert codes[5] == 429
