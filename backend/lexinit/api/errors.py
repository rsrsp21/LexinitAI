from __future__ import annotations

from typing import Any


class ApiError(Exception):
    """A safe, intentional error that can be returned to an API client."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "invalid_request",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details
