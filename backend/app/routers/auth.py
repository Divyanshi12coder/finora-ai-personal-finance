"""Authentication endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    OnboardingRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
    UserUpdate,
)
from app.schemas.common import Message
from app.services import auth_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account",
    description=(
        "Registers a user, hashes the password with bcrypt, and returns a JWT "
        "access token together with the created profile."
    ),
)
def register(payload: RegisterRequest, session: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = auth_service.register(session, payload)
    except auth_service.RegistrationError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    session.commit()
    session.refresh(user)

    token, expires_in = auth_service.issue_token(user)
    return TokenResponse(
        access_token=token, expires_in=expires_in, user=UserOut.model_validate(user)
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in",
    description="Exchanges email and password for a JWT access token.",
)
def login(payload: LoginRequest, session: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = auth_service.authenticate(session, payload.email, payload.password)
    except auth_service.AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    session.commit()
    session.refresh(user)

    token, expires_in = auth_service.issue_token(user)
    return TokenResponse(
        access_token=token, expires_in=expires_in, user=UserOut.model_validate(user)
    )


@router.post(
    "/logout",
    response_model=Message,
    summary="Log out",
    description=(
        "Logout is client-side for stateless JWTs: the client discards the token. "
        "This endpoint exists so the action is auditable server-side, and so the "
        "client has a single place to call. Tokens remain valid until they expire; "
        "a deployment needing immediate revocation would add a token denylist."
    ),
)
def logout(user: User = Depends(get_current_user)) -> Message:
    logger.info("User logged out: %s", user.id)
    return Message(detail="Logged out successfully")


@router.get("/me", response_model=UserOut, summary="Current user profile")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut, summary="Update profile")
def update_me(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> UserOut:
    updated = auth_service.update_profile(session, user, payload)
    session.commit()
    session.refresh(updated)
    return UserOut.model_validate(updated)


@router.post(
    "/onboarding",
    response_model=UserOut,
    summary="Complete onboarding",
    description=(
        "Saves the onboarding profile and creates a FinancialGoal for each goal "
        "the user selected."
    ),
)
def complete_onboarding(
    payload: OnboardingRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> UserOut:
    updated = auth_service.complete_onboarding(session, user, payload)
    session.commit()
    session.refresh(updated)
    return UserOut.model_validate(updated)


@router.post(
    "/change-password",
    response_model=Message,
    summary="Change password",
)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Message:
    try:
        auth_service.change_password(session, user, payload.current_password, payload.new_password)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return Message(detail="Password updated successfully")


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="Request a password reset",
    description=(
        "Always returns the same message whether or not the email is registered, "
        "so the endpoint cannot be used to discover which addresses have accounts. "
        "No mail transport is configured in this project, so in a non-production "
        "environment the token is returned in the response to make the flow "
        "testable; in production it is omitted and would be emailed."
    ),
)
def forgot_password(
    payload: ForgotPasswordRequest, session: Session = Depends(get_db)
) -> ForgotPasswordResponse:
    raw_token = auth_service.request_password_reset(session, payload.email)
    session.commit()

    generic = "If an account exists for that email, a password reset link has been sent."
    expose_token = settings.ENVIRONMENT.lower() != "production"
    return ForgotPasswordResponse(
        detail=generic,
        reset_token=raw_token if (expose_token and raw_token) else None,
    )


@router.post(
    "/reset-password",
    response_model=Message,
    summary="Reset a password using a token",
)
def reset_password(payload: ResetPasswordRequest, session: Session = Depends(get_db)) -> Message:
    try:
        auth_service.reset_password(session, payload.token, payload.new_password)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    session.commit()
    return Message(detail="Password reset successfully. You can now log in.")
