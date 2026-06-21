import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time

from fastapi import Cookie, HTTPException, status

from app.core.config import settings

SESSION_COOKIE_NAME = "staff_session"


def authentication_configured() -> bool:
    return bool(settings.ADMIN_PASSWORD and settings.SESSION_SECRET)


def verify_admin_password(password: str) -> bool:
    if not authentication_configured():
        return False
    return hmac.compare_digest(password, settings.ADMIN_PASSWORD)


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_session_token() -> str:
    payload = {
        "exp": int(time.time()) + settings.SESSION_TTL_SECONDS,
        "nonce": secrets.token_urlsafe(16),
        "role": "staff",
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        settings.SESSION_SECRET.encode("utf-8"),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded}.{_encode(signature)}"


def verify_session_token(token: str) -> bool:
    if not authentication_configured() or not token:
        return False
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected_signature = hmac.new(
            settings.SESSION_SECRET.encode("utf-8"),
            encoded.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_decode(supplied_signature), expected_signature):
            return False
        payload = json.loads(_decode(encoded))
        return payload.get("role") == "staff" and int(payload.get("exp", 0)) > int(time.time())
    except (ValueError, TypeError, json.JSONDecodeError, binascii.Error):
        return False


def require_staff_session(
    staff_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> None:
    if not verify_session_token(staff_session or ""):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication_required",
        )
