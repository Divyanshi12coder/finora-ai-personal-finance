"""Analytics, dashboard, forecast, insight and health-score schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import InsightSeverity, InsightType
from app.schemas.common import ORMModel
from app.schemas.transaction import TransactionOut


# --- Dashboard ---------------------------------------------------------------
class MetricCard(BaseModel):
    key: str
    label: str
    value: Decimal
    previous_value: Decimal | None = None
    change_pct: float | None = Field(
        default=None, description="Null when the previous period was zero"
    )
    trend: str = Field(description="up | down | flat")
    # Whether an increase is good. Income up = good; expenses up = bad.
    direction_is_good: bool | None = None
    unit: str = "currency"
    hint: str | None = None


class DashboardResponse(BaseModel):
    period: dict
    currency: str
    metrics: list[MetricCard]
    income_vs_expense: list[dict]
    category_breakdown: list[dict]
    daily_spending: list[dict]
    monthly_trend: list[dict]
    recent_transactions: list[TransactionOut]
    budget_summary: dict | None
    goal_summary: dict
    health_score: dict
    top_insights: list[InsightOut]
    anomaly_count: int
    has_data: bool


# --- Analytics ---------------------------------------------------------------
class CategorySpend(BaseModel):
    category_id: str | None
    category: str
    color: str
    amount: Decimal
    percentage: float
    transaction_count: int
    average: Decimal
    previous_amount: Decimal | None = None
    change_pct: float | None = None


class MerchantSpend(BaseModel):
    merchant: str
    amount: Decimal
    transaction_count: int
    average: Decimal
    last_seen: date
    category: str | None = None


class RecurringExpense(BaseModel):
    merchant: str
    category: str | None
    occurrences: int
    average_amount: Decimal
    total_amount: Decimal
    median_interval_days: float
    cadence: str = Field(description="weekly | monthly | quarterly | irregular")
    last_seen: date
    next_expected: date | None
    confidence: float


class AnalyticsResponse(BaseModel):
    period: dict
    comparison_period: dict
    currency: str
    totals: dict
    by_category: list[CategorySpend]
    by_merchant: list[MerchantSpend]
    by_month: list[dict]
    by_day: list[dict]
    by_weekday: list[dict]
    largest_expenses: list[TransactionOut]
    recurring: list[RecurringExpense]
    stats: dict
    has_data: bool


# --- Forecast ----------------------------------------------------------------
class ForecastPoint(BaseModel):
    period: str
    date: date
    value: Decimal
    lower: Decimal | None = None
    upper: Decimal | None = None
    is_forecast: bool


class ForecastSeries(BaseModel):
    name: str
    method: str
    history: list[ForecastPoint]
    forecast: list[ForecastPoint]
    model_detail: str


class ForecastResponse(BaseModel):
    sufficient_data: bool
    message: str | None = None
    months_of_history: int
    horizon_months: int
    generated_at: datetime
    currency: str
    income: ForecastSeries | None = None
    expense: ForecastSeries | None = None
    net_cashflow: list[ForecastPoint] = Field(default_factory=list)
    projected_balance: list[ForecastPoint] = Field(default_factory=list)
    limitations: list[str]
    method_explanation: str


# --- Financial health --------------------------------------------------------
class HealthComponent(BaseModel):
    key: str
    label: str
    score: float = Field(ge=0, le=100)
    weight: float
    value: str = Field(description="The underlying measurement, formatted for display")
    impact: str = Field(description="positive | neutral | negative")
    explanation: str
    available: bool = True


class HealthScoreResponse(BaseModel):
    score: float
    grade: str
    band: str
    components: list[HealthComponent]
    positives: list[str]
    negatives: list[str]
    methodology: str
    disclaimer: str
    computed_at: datetime
    has_data: bool


# --- Insights ----------------------------------------------------------------
class InsightOut(ORMModel):
    id: str
    type: InsightType
    severity: InsightSeverity
    title: str
    summary: str
    why_it_matters: str | None
    suggested_action: str | None
    ai_explanation: str | None
    data: dict | None
    period_start: date | None
    period_end: date | None
    is_read: bool
    is_dismissed: bool
    created_at: datetime


class InsightGenerateResponse(BaseModel):
    generated: int
    insights: list[InsightOut]
    ai_enabled: bool
    note: str | None = None


# --- Anomalies ---------------------------------------------------------------
class AnomalyOut(BaseModel):
    transaction: TransactionOut
    score: float
    reason: str
    detail: dict


class AnomalyResponse(BaseModel):
    sufficient_data: bool
    message: str | None = None
    method: str
    analyzed_transactions: int
    anomalies: list[AnomalyOut]
    baseline: dict
    explanation: str


DashboardResponse.model_rebuild()
