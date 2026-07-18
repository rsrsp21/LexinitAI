import base64
import json
import os
import random
import time
from functools import lru_cache

from google import genai
from google.genai import types
from google.cloud import vision
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pydantic import BaseModel, ValidationError


def _env(name):
    return os.environ.get(name)


class GeminiModel:
    def __init__(self, api_key, model_name, fallback_model_names=None):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.fallback_model_names = fallback_model_names or []

    def generate_content(self, prompt):
        last_error = None
        for model_name in [self.model_name, *self.fallback_model_names]:
            for attempt in range(3):
                try:
                    return self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                    )
                except Exception as exc:
                    last_error = exc
                    if not _is_transient_ai_error(exc) or attempt == 2:
                        break
                    time.sleep((0.8 * (2**attempt)) + random.uniform(0, 0.35))

        if last_error and _is_transient_ai_error(last_error):
            raise RuntimeError(
                "The AI model is temporarily busy. Please try again in a minute."
            ) from last_error
        if last_error:
            raise last_error
        raise RuntimeError("The AI model did not return a response.")

    def generate_structured(
        self,
        prompt: str,
        response_schema: type[BaseModel],
        *,
        temperature: float = 0.2,
    ) -> BaseModel:
        """Generate and validate JSON output against a Pydantic contract."""
        last_error = None
        for model_name in [self.model_name, *self.fallback_model_names]:
            for attempt in range(3):
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_json_schema=_gemini_json_schema(response_schema),
                            temperature=temperature,
                        ),
                    )
                    parsed = getattr(response, "parsed", None)
                    if isinstance(parsed, response_schema):
                        return parsed
                    if parsed is not None:
                        return response_schema.model_validate(parsed)
                    text = getattr(response, "text", None)
                    if text:
                        return response_schema.model_validate_json(text)
                    raise ValueError("The AI model returned no structured content.")
                except Exception as exc:
                    last_error = exc
                    invalid_structure = isinstance(exc, (ValidationError, ValueError, json.JSONDecodeError))
                    if invalid_structure and attempt < 1:
                        continue
                    if not _is_transient_ai_error(exc) or attempt == 2:
                        break
                    time.sleep((0.8 * (2**attempt)) + random.uniform(0, 0.35))

        if isinstance(last_error, (ValidationError, ValueError, json.JSONDecodeError)):
            raise RuntimeError("The AI model returned content that failed validation.") from last_error
        if last_error and _is_transient_ai_error(last_error):
            raise RuntimeError(
                "The AI model is temporarily busy. Please try again in a minute."
            ) from last_error
        if last_error:
            raise last_error
        raise RuntimeError("The AI model did not return a response.")


def _gemini_json_schema(response_model: type[BaseModel]) -> dict:
    """Return a Gemini-compatible JSON Schema.

    Pydantic still validates the returned payload locally.  Gemini's structured
    output endpoint rejects deeply nested size, pattern, and numeric constraints
    as an oversized state space, so those constraints must stay local.
    """

    unsupported_constraints = {
        "additionalProperties",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "pattern",
        "format",
    }

    def clean(value):
        if isinstance(value, dict):
            return {
                key: clean(item)
                for key, item in value.items()
                if key not in unsupported_constraints
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(response_model.model_json_schema())


def _is_transient_ai_error(error):
    text = str(error).lower()
    transient_markers = (
        "503",
        "429",
        "unavailable",
        "resource_exhausted",
        "rate limit",
        "quota",
        "high demand",
        "temporarily",
        "try again later",
    )
    return any(marker in text for marker in transient_markers)


def _env_list(name):
    return [item.strip() for item in (_env(name) or "").split(",") if item.strip()]


def _fallback_tuple(fallback_model_names):
    if fallback_model_names is None:
        return tuple(_env_list("GEMINI_FALLBACK_MODEL_NAMES"))
    return tuple(fallback_model_names)


@lru_cache(maxsize=16)
def _get_gemini_model_cached(model_name, fallback_model_names):
    return GeminiModel(
        api_key=_env("GEMINI_API_KEY"),
        model_name=model_name,
        fallback_model_names=list(fallback_model_names),
    )


def get_gemini_model(model_name=None, fallback_model_names=None):
    primary_model = model_name or _env("GEMINI_MODEL_NAME") or "gemini-2.5-flash-lite"
    return _get_gemini_model_cached(primary_model, _fallback_tuple(fallback_model_names))


@lru_cache(maxsize=1)
def get_google_credentials():
    encoded_credentials = _env("GOOGLE_CREDENTIALS_BASE64")
    if not encoded_credentials:
        raise RuntimeError("GOOGLE_CREDENTIALS_BASE64 is not configured.")

    credentials_json = base64.b64decode(encoded_credentials).decode()
    credentials_dict = json.loads(credentials_json)
    return service_account.Credentials.from_service_account_info(credentials_dict)


@lru_cache(maxsize=1)
def get_vision_client():
    return vision.ImageAnnotatorClient(credentials=get_google_credentials())


@lru_cache(maxsize=1)
def get_youtube_client():
    return build("youtube", "v3", developerKey=_env("YOUTUBE_API_KEY"))


@lru_cache(maxsize=1)
def get_youtube_client_with_credentials():
    return build("youtube", "v3", credentials=get_google_credentials())
