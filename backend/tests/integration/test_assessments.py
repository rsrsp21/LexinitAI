"""Module assessments end to end over HTTP: attempts, results, progress."""

import uuid


def key(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"


def start(client, course, module_id, kind):
    response = client.post(
        f"/api/v1/sessions/{course['_id']}/assessment-attempts",
        json={"assessment_type": kind, "question_count": 2, "module_id": module_id},
        headers={"Idempotency-Key": key("start")},
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()


def take(client, db, attempt, *, wrong=0):
    """Answer every question, getting the first ``wrong`` of them wrong."""
    asked = []
    index = 0
    while attempt["status"] == "active":
        question = attempt["current_question"]
        asked.append(question)
        stored = db.assessment_question_bank.find_one({"_id": question["question_id"]})["payload"]
        answer = stored["answer"]
        if index < wrong:
            if isinstance(answer, bool):
                answer = not answer
            elif isinstance(answer, int):
                answer = (answer + 1) % 4
            else:
                answer = "wrongword"
        attempt = client.post(
            f"/api/v1/assessment-attempts/{attempt['attempt_id']}/answers",
            json={"question_id": question["question_id"], "answer": answer},
            headers={"Idempotency-Key": key("answer")},
        ).get_json()
        index += 1
    result = client.post(
        f"/api/v1/assessment-attempts/{attempt['attempt_id']}/submit",
        json={"submission_token": attempt["submission_token"]},
        headers={"Idempotency-Key": key("submit")},
    )
    assert result.status_code == 200, result.get_json()
    return result.get_json(), asked


def module_ids(course):
    return [module["module_id"] for module in course["curriculum"]["modules"]]


def test_course_payload_hides_answers(client, course):
    public = client.get(f"/api/v1/sessions/{course['_id']}").get_json()["session"]
    for field in ("mcqs", "true_false", "oneword"):
        for question in public[field]:
            assert not {"answer", "explanation", "misconception_map"} & set(question)


def test_a_module_assessment_has_four_questions_from_that_module(client, db, course):
    module_id = module_ids(course)[1]
    attempt = start(client, course, module_id, "mcq")
    assert attempt["target_count"] == 4
    assert "answer" not in attempt["current_question"]
    result, asked = take(client, db, attempt)
    assert (result["score"], result["total"]) == (4, 4)
    assert len({question["question_id"] for question in asked}) == 4
    assert {question["module_id"] for question in asked} == {module_id}


def test_a_reattempt_uses_questions_not_seen_before(client, db, course):
    module_id = module_ids(course)[0]
    _, first = take(client, db, start(client, course, module_id, "truefalse"))
    _, second = take(client, db, start(client, course, module_id, "truefalse"))
    first_ids = {question["question_id"] for question in first}
    second_ids = {question["question_id"] for question in second}
    assert len(second_ids) == 4 and not first_ids & second_ids


def test_starting_twice_with_the_same_key_returns_the_same_attempt(client, course):
    headers = {"Idempotency-Key": key("start")}
    body = {"assessment_type": "mcq", "question_count": 2, "module_id": module_ids(course)[0]}
    url = f"/api/v1/sessions/{course['_id']}/assessment-attempts"
    first = client.post(url, json=body, headers=headers).get_json()
    second = client.post(url, json=body, headers=headers).get_json()
    assert first["attempt_id"] == second["attempt_id"]


def test_submitting_needs_every_answer_and_the_right_token(client, db, course):
    attempt = start(client, course, module_ids(course)[0], "mcq")
    early = client.post(
        f"/api/v1/assessment-attempts/{attempt['attempt_id']}/submit",
        json={"submission_token": attempt["submission_token"]},
        headers={"Idempotency-Key": key("submit")},
    )
    assert early.status_code == 409
    forged = client.post(
        f"/api/v1/assessment-attempts/{attempt['attempt_id']}/submit",
        json={"submission_token": "0" * 64},
        headers={"Idempotency-Key": key("submit")},
    )
    assert forged.status_code == 403


def test_a_module_passes_at_fifty_percent_on_every_type(client, db, course):
    module_id = module_ids(course)[0]

    def module_state():
        overview = client.get(f"/api/v1/sessions/{course['_id']}/course").get_json()
        return overview, overview["modules"][0]

    take(client, db, start(client, course, module_id, "mcq"), wrong=2)  # 2 of 4
    take(client, db, start(client, course, module_id, "truefalse"), wrong=3)  # 1 of 4
    overview, module = module_state()
    assert module["passed"] is False
    assert overview["current_module_id"] == module_id
    assert all(item["status"] != "locked" for item in overview["modules"])

    take(client, db, start(client, course, module_id, "truefalse"))  # best is now 4 of 4
    take(client, db, start(client, course, module_id, "oneword"), wrong=2)
    overview, module = module_state()
    assert module["passed"] is True
    assert overview["current_module_id"] == module_ids(course)[1]
    types = next(a for a in module["activities"] if a["type"] == "assessment")["assessment_types"]
    assert {item["type"]: item["passed"] for item in types} == {
        "mcq": True,
        "truefalse": True,
        "oneword": True,
    }
    # A pass is kept even if a later attempt scores lower.
    take(client, db, start(client, course, module_id, "mcq"), wrong=4)
    assert module_state()[1]["passed"] is True


def test_one_word_answers_forgive_a_typo(client, db, course):
    attempt = start(client, course, module_ids(course)[2], "oneword")
    while attempt["status"] == "active":
        attempt = client.post(
            f"/api/v1/assessment-attempts/{attempt['attempt_id']}/answers",
            json={"question_id": attempt["current_question"]["question_id"], "answer": "Photosynthesys"},
            headers={"Idempotency-Key": key("answer")},
        ).get_json()
    result = client.post(
        f"/api/v1/assessment-attempts/{attempt['attempt_id']}/submit",
        json={"submission_token": attempt["submission_token"]},
        headers={"Idempotency-Key": key("submit")},
    ).get_json()
    assert result["score"] == result["total"] == 4


def test_results_keep_question_details_and_update_mastery(client, db, course, user):
    module_id = module_ids(course)[3]
    result, _ = take(client, db, start(client, course, module_id, "mcq"), wrong=1)
    submission = db.assessment_submissions.find_one({"user_id": user["_id"], "module_id": module_id})
    assert len(submission["question_refs"]) == 4
    assert all(ref["bank_question_id"] and ref["concept_ids"] for ref in submission["question_refs"])
    detail = client.get(f"/api/v1/assessment-submissions/{result['submission_id']}").get_json()
    assert detail["concepts"] and detail["concepts"][0]["missed"] == 1
    assert db.concept_mastery.count_documents({"user_id": user["_id"]}) >= 1
    assert db.mastery_evidence.find_one({"user_id": user["_id"]})["guess_probability"] == 0.25


def test_a_reported_question_is_not_asked_again(client, db, course, user):
    module_id = module_ids(course)[4]
    result, asked = take(client, db, start(client, course, module_id, "mcq"))
    report = client.post(
        "/api/v1/question-reports",
        json={
            "source": "assessment",
            "reference_id": result["submission_id"],
            "question_index": 0,
            "reason": "wrong_answer",
        },
    )
    assert report.status_code == 201
    flagged = db.assessment_question_bank.find_one({"user_id": user["_id"], "reported": True})
    assert flagged["_id"] == asked[0]["question_id"]
    assert db.question_reports.count_documents({"user_id": user["_id"]}) == 1
