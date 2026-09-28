"""Shared FastAPI dependencies.

``get_current_user`` is the single gate every protected endpoint passes through.
Routers then scope their queries by ``user.id``, which is how per-user data
isolation is enforced - see also the repository layer, where no query helper
accepts a request without an owner.
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.utils.security import decode_token

logger = logging.getLogger(__name__)

# auto_error=False so a missing header produces our own 401 with a clear message
# rather than FastAPI's terse default.
bearer_scheme = HTTPBearer(auto_error=False, description="JWT access token")

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated. Provide a valid bearer token.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise CREDENTIALS_EXCEPTION

    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise CREDENTIALS_EXCEPTION

    user_id = payload.get("sub")
    if not user_id:
        raise CREDENTIALS_EXCEPTION

    user = session.get(User, user_id)
    if user is None:
        # A valid signature for a deleted account.
        logger.warning("Token referenced a non-existent user %s", user_id)
        raise CREDENTIALS_EXCEPTION

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    return user


def get_onboarded_user(user: User = Depends(get_current_user)) -> User:
    """For endpoints that need the onboarding profile to be meaningful."""
    if not user.onboarding_completed:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="Please complete onboarding first.",
        )
    return user


def not_found(resource: str = "Resource") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} not found")


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
