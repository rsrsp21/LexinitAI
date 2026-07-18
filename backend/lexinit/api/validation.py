from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from backend.lexinit.api.errors import ApiError


ModelT = TypeVar("ModelT", bound=BaseModel)


GENERATION_FIELD_MESSAGES = {
    "topic": "Enter a clear topic between 2 and 500 characters without hidden or control characters.",
    "difflevel": "Difficulty must be Easy, Medium, or Hard.",
    "mode": "Invalid generation mode.",
    "assessment_submission_id": "Invalid assessment submission id.",
    "source_ids": "Choose up to five valid sources.",
}


def parse_json_model(
    model: type[ModelT],
    payload: Any,
    *,
    field_messages: dict[str, str] | None = None,
) -> ModelT:
    if not isinstance(payload, dict):
        raise ApiError("A JSON request body is required.", code="json_body_required")

    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        location = first_error.get("loc") or ()
        field = str(location[0]) if location else ""
        message = (field_messages or {}).get(field, "The request contains invalid data.")
        raise ApiError(
            message,
            code="validation_error",
            details={"field": field} if field else None,
        ) from exc
