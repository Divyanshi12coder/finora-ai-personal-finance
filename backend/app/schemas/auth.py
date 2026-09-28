"""Authentication and user-profile schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.models.enums import BudgetingPreference
from app.schemas.common import ORMModel

PASSWORD_MIN_LENGTH = 8


def _validate_password(value: str) -> str:
    """Enforce a minimum strength floor server-side.

    Client-side meters are a UX affordance, not a control: the rule has to live
    where it cannot be bypassed.
    """
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
    if not any(c.isalpha() for c in value):
        raise ValueError("Password must contain at least one letter")
    if not any(c.isdigit() for c in value):
        raise ValueError("Password must contain at least one number")
    return value


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)
    currency: str = Field(default="INR", min_length=3, max_length=3)

    _check_password = field_validator("password")(_validate_password)

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Name cannot be empty")
        return cleaned


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")
    user: UserOut


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    detail: str
    # In development the token is returned directly because no mail transport is
    # configured. In production this field is null and the token is emailed.
    reset_token: str | None = None


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=10, max_length=256)
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)

    _check_password = field_validator("new_password")(_validate_password)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=128)

    _check_password = field_validator("new_password")(_validate_password)


class UserOut(ORMModel):
    id: str
    email: EmailStr
    full_name: str
    currency: str
    monthly_income: Decimal | None = None
    income_source: str | None = None
    typical_monthly_expenses: Decimal | None = None
    savings_goal_amount: Decimal | None = None
    emergency_fund_target: Decimal | None = None
    budgeting_preference: BudgetingPreference
    onboarding_completed: bool
    created_at: datetime
    last_login_at: datetime | None = None


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    monthly_income: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))
    income_source: str | None = Field(default=None, max_length=80)
    typical_monthly_expenses: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))
    savings_goal_amount: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))
    emergency_fund_target: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))
    budgeting_preference: BudgetingPreference | None = None


class OnboardingRequest(BaseModel):
    """Payload submitted at the end of the onboarding wizard."""

    monthly_income: Decimal = Field(ge=0, le=Decimal("99999999.99"))
    income_source: str = Field(min_length=1, max_length=80)
    typical_monthly_expenses: Decimal = Field(ge=0, le=Decimal("99999999.99"))
    savings_goal_amount: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))
    emergency_fund_target: Decimal | None = Field(default=None, ge=0, le=Decimal("99999999.99"))
    currency: str = Field(default="INR", min_length=3, max_length=3)
    budgeting_preference: BudgetingPreference = BudgetingPreference.BALANCED
    # Goals the user picked during onboarding; each becomes a FinancialGoal.
    goals: list[OnboardingGoal] = Field(default_factory=list, max_length=6)


class OnboardingGoal(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: Decimal = Field(gt=0, le=Decimal("99999999.99"))
    target_date: str | None = None
    goal_type: str = Field(default="savings", max_length=40)


TokenResponse.model_rebuild()
OnboardingRequest.model_rebuild()
