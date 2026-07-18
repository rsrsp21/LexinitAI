import re


SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def clean_string(value, *, max_length, min_length=0):
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if len(cleaned) < min_length or len(cleaned) > max_length:
        return None
    return cleaned


def valid_safe_id(value):
    return isinstance(value, str) and bool(SAFE_ID_RE.fullmatch(value))


def valid_video_id(value):
    return isinstance(value, str) and bool(VIDEO_ID_RE.fullmatch(value))


def validate_password(value):
    if not isinstance(value, str):
        return "Password must be text."
    if len(value) < 8:
        return "Password must be at least 8 characters."
    if len(value) > 128:
        return "Password must be 128 characters or fewer."
    if not re.search(r"[A-Za-z]", value):
        return "Password must include at least one letter."
    if not re.search(r"\d", value):
        return "Password must include at least one number."
    return None
