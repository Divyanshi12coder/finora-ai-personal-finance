"""Password hashing and JWT issuance/verification.

Passwords are hashed with bcrypt (adaptive, salted). Plain-text passwords are
never stored, never logged, and never returned by any schema.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import settings

logger = logging.getLogger(__name__)

# bcrypt operates on at most 72 bytes and silently truncates beyond that. Long
# passphrases are pre-hashed with SHA-256 so every byte contributes to the
# resulting hash instead of being discarded.
_BCRYPT_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    raw = password.encode("utf-8")
    if len(raw) > _BCRYPT_MAX_BYTES:
        return hashlib.sha256(raw).hexdigest().encode("ascii")
    return raw


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_prepare(password), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed hash in the database - treat as a failed login, never a 500.
        logger.warning("Password verification failed due to a malformed hash")
        return False


def create_access_token(
    subject: str,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
        "jti": secrets.token_urlsafe(16),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any] | None:
    """Return the token payload, or ``None`` if it is invalid or expired."""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        logger.info("Rejected an expired token")
        return None
    except jwt.InvalidTokenError as exc:
        logger.info("Rejected an invalid token: %s", exc)
        return None


def generate_reset_token() -> tuple[str, str]:
    """Return ``(raw_token, token_hash)``.

    The raw token goes to the user; only the hash is persisted, so a database
    dump cannot be replayed to reset someone's password.
    """
    raw = secrets.token_urlsafe(32)
    return raw, hash_reset_token(raw)


def hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
