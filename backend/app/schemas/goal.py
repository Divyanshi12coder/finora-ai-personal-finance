"""Financial goal schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import GoalStatus
from app.schemas.common import ORMModel

MAX_AMOUNT = Decimal("99999999.99")


class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: Decimal = Field(gt=0, le=MAX_AMOUNT)
    current_amount: Decimal = Field(default=Decimal("0"), ge=0, le=MAX_AMOUNT)
    target_date: date | None = None
    goal_type: str = Field(default="savings", max_length=40)
    icon: str = Field(default="Target", max_length=40)
    color: str = Field(default="#0B1F3A", pattern=r"^#(?:[0-9a-fA-F]{3,4}){1,2}$")
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("target_date")
    @classmethod
    def _future(cls, value: date | None) -> date | None:
        if value and value < date.today():
            raise ValueError("Target date must be in the future")
        return value


class GoalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_amount: Decimal | None = Field(default=None, gt=0, le=MAX_AMOUNT)
    target_date: date | None = None
    goal_type: str | None = Field(default=None, max_length=40)
    icon: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, pattern=r"^#(?:[0-9a-fA-F]{3,4}){1,2}$")
    notes: str | None = Field(default=None, max_length=1000)
    status: GoalStatus | None = None


class ContributionCreate(BaseModel):
    amount: Decimal = Field(description="Positive to add, negative to withdraw")
    occurred_on: date | None = None
    note: str | None = Field(default=None, max_length=200)

    @field_validator("amount")
    @classmethod
    def _nonzero(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("Contribution amount cannot be zero")
        if abs(value) > MAX_AMOUNT:
            raise ValueError("Contribution amount is out of range")
        return value


class ContributionOut(ORMModel):
    id: str
    amount: Decimal
    occurred_on: date
    note: str | None
    created_at: datetime


class GoalOut(ORMModel):
    id: str
    name: str
    goal_type: str
    target_amount: Decimal
    current_amount: Decimal
    target_date: date | None
    status: GoalStatus
    icon: str
    color: str
    notes: str | None
    created_at: datetime
    # --- computed ---
    progress_pct: float
    remaining: Decimal
    months_remaining: int | None
    suggested_monthly_contribution: Decimal | None
    projected_completion: date | None
    on_track: bool | None
    pace_note: str
    contributions: list[ContributionOut] = Field(default_factory=list)
