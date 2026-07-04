import hashlib
import hmac
import secrets
import time
import uuid
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from core.config import get_settings
from core.exceptions import AuthenticationError

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(*, user_id: uuid.UUID, org_id: uuid.UUID, role: str) -> str:
    s = get_settings()
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "org": str(org_id),
        "role": role,
        "iat": now,
        "exp": now + s.jwt_access_ttl_seconds,
        "type": "access",
    }
    return jwt.encode(payload, s.app_secret_key, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.app_secret_key, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired token") from exc
    if payload.get("type") != "access":
        raise AuthenticationError("Wrong token type")
    return payload


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def new_api_key() -> str:
    return f"kmb_{secrets.token_urlsafe(36)}"


def hash_token(token: str) -> str:
    """Opaque tokens (refresh, API keys) stored only as SHA-256 digests."""
    return hashlib.sha256(token.encode()).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
