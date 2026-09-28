"""Authentication and user-account business logic."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import FinancialGoal, GoalStatus, User
from app.schemas.auth import OnboardingRequest, RegisterRequest, UserUpdate
from app.utils.security import (
    create_access_token,
    generate_reset_token,
    hash_password,
    hash_reset_token,
    verify_password,
)

logger = logging.getLogger(__name__)


class AuthError(Exception):
    """Authentication failure; routers map this to a 401."""


class RegistrationError(Exception):
    """Registration failure; routers map this to a 400/409."""


def get_by_email(session: Session, email: str) -> User | None:
    # Emails are stored and compared lowercase so Bob@x.com and bob@x.com are
    # the same account.
    stmt = select(User).where(User.email == email.lower().strip())
    return session.scalars(stmt).first()


def get_by_id(session: Session, user_id: str) -> User | None:
    return session.get(User, user_id)


def register(session: Session, payload: RegisterRequest) -> User:
    email = payload.email.lower().strip()
    if get_by_email(session, email) is not None:
        raise RegistrationError("An account with this email already exists")

    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        currency=payload.currency.upper(),
    )
    session.add(user)
    session.flush()

    # Make sure the shared category set exists for a brand-new install.
    from app.services import category_service

    category_service.ensure_system_categories(session)

    logger.info("User registered: %s", email)
    return user


def authenticate(session: Session, email: str, password: str) -> User:
    user = get_by_email(session, email)

    # Always run a hash comparison, even when the account does not exist, so the
    # response time does not reveal whether an email is registered.
    if user is None:
        hash_password(password)
        logger.info("Failed login for unknown email")
        raise AuthError("Incorrect email or password")

    if not verify_password(password, user.hashed_password):
        logger.info("Failed login for user %s", user.id)
        raise AuthError("Incorrect email or password")

    if not user.is_active:
        logger.warning("Login attempt on a deactivated account %s", user.id)
        raise AuthError("This account has been deactivated")

    user.last_login_at = datetime.now(UTC)
    session.flush()
    logger.info("User logged in: %s", user.id)
    return user


def issue_token(user: User) -> tuple[str, int]:
    token = create_access_token(subject=user.id, extra_claims={"email": user.email})
    return token, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def update_profile(session: Session, user: User, payload: UserUpdate) -> User:
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user, field, value.upper() if field == "currency" else value)
    session.flush()
    return user


def complete_onboarding(session: Session, user: User, payload: OnboardingRequest) -> User:
    user.monthly_income = payload.monthly_income
    user.income_source = payload.income_source
    user.typical_monthly_expenses = payload.typical_monthly_expenses
    user.savings_goal_amount = payload.savings_goal_amount
    user.currency = payload.currency.upper()
    user.budgeting_preference = payload.budgeting_preference
    user.emergency_fund_target = payload.emergency_fund_target or (
        payload.typical_monthly_expenses * 6 if payload.typical_monthly_expenses else None
    )
    user.onboarding_completed = True

    # The goals chosen during onboarding become real, trackable goals.
    from datetime import date

    for goal in payload.goals:
        target_date = None
        if goal.target_date:
            try:
                target_date = date.fromisoformat(goal.target_date)
            except ValueError:
                logger.warning("Ignoring invalid onboarding goal date %r", goal.target_date)

        session.add(
            FinancialGoal(
                user_id=user.id,
                name=goal.name,
                goal_type=goal.goal_type,
                target_amount=goal.target_amount,
                current_amount=0,
                target_date=target_date,
                status=GoalStatus.ACTIVE,
            )
        )

    session.flush()
    logger.info("Onboarding completed for user %s with %d goals", user.id, len(payload.goals))
    return user


def change_password(session: Session, user: User, current_password: str, new_password: str) -> User:
    if not verify_password(current_password, user.hashed_password):
        raise AuthError("Your current password is incorrect")
    user.hashed_password = hash_password(new_password)
    session.flush()
    logger.info("Password changed for user %s", user.id)
    return user


def request_password_reset(session: Session, email: str) -> str | None:
    """Create a reset token. Returns the raw token, or ``None`` if no account.

    The caller must respond identically either way, so the endpoint does not
    become an account-enumeration oracle.
    """
    user = get_by_email(session, email)
    if user is None:
        logger.info("Password reset requested for an unknown email")
        return None

    raw_token, token_hash = generate_reset_token()
    user.reset_token_hash = token_hash
    user.reset_token_expires_at = datetime.now(UTC) + timedelta(
        minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES
    )
    session.flush()
    logger.info("Password reset token issued for user %s", user.id)
    return raw_token


def reset_password(session: Session, raw_token: str, new_password: str) -> User:
    token_hash = hash_reset_token(raw_token)
    stmt = select(User).where(User.reset_token_hash == token_hash)
    user = session.scalars(stmt).first()

    if user is None:
        raise AuthError("This reset link is invalid or has already been used")

    expires_at = user.reset_token_expires_at
    if expires_at is None:
        raise AuthError("This reset link is invalid or has already been used")

    # SQLite can return a naive datetime; normalise before comparing.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        raise AuthError("This reset link has expired. Please request a new one.")

    user.hashed_password = hash_password(new_password)
    # Single-use: clear the token so the link cannot be replayed.
    user.reset_token_hash = None
    user.reset_token_expires_at = None
    session.flush()
    logger.info("Password reset completed for user %s", user.id)
    return user
