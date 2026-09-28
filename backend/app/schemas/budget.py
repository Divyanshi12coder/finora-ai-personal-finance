"""Budget schemas.

Note the asymmetry: budget *inputs* carry only limits, while budget *outputs*
carry spent/remaining/utilisation/pace figures computed from transactions. The
client never sends a "spent" value, so it can never be wrong.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import ORMModel
from app.schemas.transaction import CategoryOut

MAX_AMOUNT = Decimal("99999999.99")


class BudgetItemCreate(BaseModel):
    category_id: str
    limit_amount: Decimal = Field(gt=0, le=MAX_AMOUNT)


class BudgetCreate(BaseModel):
    name: str = Field(default="Monthly budget", min_length=1, max_length=80)
    # "2026-09" or a full ISO date; normalised to the first of the month.
    period_month: str
    total_limit: Decimal | None = Field(default=None, gt=0, le=MAX_AMOUNT)
    notes: str | None = Field(default=None, max_length=1000)
    items: list[BudgetItemCreate] = Field(default_factory=list, max_length=40)

    @field_validator("period_month")
    @classmethod
    def _valid_period(cls, value: str) -> str:
        from app.utils.dates import parse_month_key

        try:
            parse_month_key(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("period_month must look like '2026-09' or an ISO date") from exc
        return value


class BudgetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    total_limit: Decimal | None = Field(default=None, gt=0, le=MAX_AMOUNT)
    notes: str | None = Field(default=None, max_length=1000)
    items: list[BudgetItemCreate] | None = Field(default=None, max_length=40)


class BudgetItemStatus(BaseModel):
    id: str
    category: CategoryOut
    limit_amount: Decimal
    spent: Decimal
    remaining: Decimal
    utilization: float = Field(description="Percent of the limit used, 0-100+")
    status: str = Field(description="on_track | watch | at_risk | exceeded")
    transaction_count: int
    daily_average: Decimal
    projected_spend: Decimal = Field(description="Month-end projection at the current pace")
    projected_overspend: Decimal
    recommended_amount: Decimal | None = None
    recommendation_basis: str | None = None
    warning: str | None = None


class BudgetOut(ORMModel):
    id: str
    name: str
    period_month: date
    period_label: str
    total_limit: Decimal | None
    notes: str | None
    # --- computed from transactions ---
    allocated: Decimal
    spent: Decimal
    remaining: Decimal
    utilization: float
    days_total: int
    days_elapsed: int
    days_remaining: int
    expected_utilization: float = Field(
        description="Percent of the month elapsed - the pace a linear spender would be at"
    )
    status: str
    items: list[BudgetItemStatus]
    warnings: list[str] = Field(default_factory=list)


class BudgetRecommendationItem(BaseModel):
    category_id: str
    category_name: str
    recommended_amount: Decimal
    current_limit: Decimal | None
    method: str = Field(description="Statistic used, e.g. trimmed_mean_plus_buffer")
    confidence: str = Field(description="low | medium | high")
    months_analyzed: int
    monthly_history: list[dict]
    mean: Decimal
    median: Decimal
    std_dev: Decimal
    trend_pct: float | None
    rationale: str = Field(description="Plain-English explanation of why this number")


class BudgetRecommendationResponse(BaseModel):
    period_month: str
    generated_at: str
    months_analyzed: int
    sufficient_data: bool
    message: str | None = None
    total_recommended: Decimal
    items: list[BudgetRecommendationItem]
    methodology: str


class ApplyRecommendationRequest(BaseModel):
    period_month: str
    category_ids: list[str] | None = Field(
        default=None, description="Apply only these categories; omit for all"
    )
