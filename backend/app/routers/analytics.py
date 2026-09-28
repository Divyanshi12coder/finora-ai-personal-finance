"""Dashboard, analytics, forecasting, health-score and anomaly endpoints."""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.schemas.analytics import (
    AnalyticsResponse,
    AnomalyOut,
    AnomalyResponse,
    DashboardResponse,
    ForecastResponse,
    HealthScoreResponse,
)
from app.schemas.transaction import TransactionOut
from app.services import (
    analytics_service,
    anomaly_service,
    dashboard_service,
    forecasting_service,
    health_service,
)
from app.utils.dates import resolve_range

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analytics"])

RANGE_DESCRIPTION = (
    "Preset window: 7d, 30d, 3m, 6m, 1y, mtd or all. Ignored when explicit "
    "start/end dates are supplied."
)


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Complete dashboard payload",
    description=(
        "Assembles the whole dashboard in one request: headline metrics with "
        "period-over-period change, income vs expense trend, category breakdown, "
        "daily spend, recent transactions, budget summary, goal summary, financial "
        "health score, top insights and the unusual-transaction count. Every value "
        "is computed from the database."
    ),
)
def dashboard(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> DashboardResponse:
    data = dashboard_service.build_dashboard(session, user)
    session.commit()  # health/insight computation may persist anomaly scores
    return DashboardResponse.model_validate(data)


@router.get(
    "/analytics/spending",
    response_model=AnalyticsResponse,
    summary="Spending analytics",
    description=(
        "Category, merchant, monthly, daily and weekday breakdowns, largest "
        "expenses, detected recurring charges and summary statistics for the "
        "selected window, each compared against the immediately preceding window "
        "of identical length."
    ),
)
def spending_analytics(
    range: str = Query(default="30d", description=RANGE_DESCRIPTION),
    start: date | None = None,
    end: date | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> AnalyticsResponse:
    period = resolve_range(preset=range, start=start, end=end)
    data = analytics_service.build_analytics(session, user, period)
    data["largest_expenses"] = [TransactionOut.model_validate(t) for t in data["largest_expenses"]]
    return AnalyticsResponse.model_validate(data)


@router.get(
    "/forecast",
    response_model=ForecastResponse,
    summary="Cash-flow forecast",
    description=(
        "Forecasts monthly income, expenses and net cash flow. The model is chosen "
        "by how much history exists (Holt-Winters at 24+ months, damped Holt's "
        "trend at 12+, simple exponential smoothing at 6+, weighted moving average "
        "at 3+), and below three complete months the endpoint declines to forecast "
        "and explains why. Includes an 80% prediction interval and explicit "
        "limitations."
    ),
)
def forecast(
    horizon: int = Query(default=3, ge=1, le=12, description="Months to project"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ForecastResponse:
    return ForecastResponse.model_validate(
        forecasting_service.build_forecast(session, user, horizon=horizon)
    )


@router.get(
    "/health-score",
    response_model=HealthScoreResponse,
    summary="Financial health score",
    description=(
        "A transparent, weighted score over six measurable components. Each "
        "component returns its own sub-score, the underlying measurement and an "
        "explanation. Components that cannot be measured are excluded and the "
        "remaining weights renormalised. This is an educational metric, not a "
        "credit score or professional advice."
    ),
)
def health_score(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> HealthScoreResponse:
    return HealthScoreResponse.model_validate(health_service.compute_health_score(session, user))


@router.get(
    "/anomalies",
    response_model=AnomalyResponse,
    summary="Unusual spending detection",
    description=(
        "Runs the anomaly detectors over the user's own expense history: a "
        "MAD-based modified z-score per category, plus an Isolation Forest over "
        "amount, category-relative size, timing, merchant familiarity and recency. "
        "Each flagged transaction includes the reason and the baseline it was "
        "compared against. Requires at least 12 expenses."
    ),
)
def anomalies(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> AnomalyResponse:
    result = anomaly_service.run_detection(session, user)
    session.commit()

    return AnomalyResponse(
        sufficient_data=result["sufficient_data"],
        message=result["message"],
        method=result["method"],
        analyzed_transactions=result["analyzed_transactions"],
        anomalies=[
            AnomalyOut(
                transaction=TransactionOut.model_validate(entry["transaction"]),
                score=entry["score"],
                reason=entry["reason"],
                detail=entry["detail"],
            )
            for entry in result["anomalies"]
        ],
        baseline=result["baseline"],
        explanation=result["explanation"],
    )
