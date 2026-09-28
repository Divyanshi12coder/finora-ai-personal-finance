"""Cash-flow forecasting orchestration.

Aggregates the user's transactions into monthly income/expense series, runs the
forecaster, and assembles the response the chart consumes. Partial months are
excluded from the fit: the current month is incomplete by definition, and
including it drags every forecast downward.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.ml import forecasting
from app.models import TransactionType, User
from app.repositories import transaction_repository as repo
from app.utils.dates import add_months, iter_months, month_key, month_label, month_start
from app.utils.money import quantize

logger = logging.getLogger(__name__)

DEFAULT_HORIZON = 3
MAX_HORIZON = 12


def _monthly_series(
    session: Session, user: User, today: date
) -> tuple[list[date], list[float], list[float]]:
    """Return ``(months, income_totals, expense_totals)`` for complete months only."""
    earliest = repo.earliest_date(session, user.id)
    if earliest is None:
        return [], [], []

    # The current month is incomplete, so it informs nothing and is excluded.
    last_complete = add_months(month_start(today), -1)
    if month_start(earliest) > last_complete:
        return [], [], []

    transactions = repo.list_in_range(session, user.id, earliest, today)

    income: dict[str, Decimal] = {}
    expense: dict[str, Decimal] = {}
    for t in transactions:
        key = month_key(t.occurred_on)
        if t.type == TransactionType.INCOME:
            income[key] = income.get(key, Decimal("0")) + Decimal(t.amount)
        elif t.type == TransactionType.EXPENSE:
            expense[key] = expense.get(key, Decimal("0")) + Decimal(t.amount)

    months = list(iter_months(earliest, last_complete))
    income_values = [float(income.get(month_key(m), Decimal("0"))) for m in months]
    expense_values = [float(expense.get(month_key(m), Decimal("0"))) for m in months]
    return months, income_values, expense_values


def _points(
    months: list[date],
    values: list[float],
    is_forecast: bool = False,
    lower: list[float] | None = None,
    upper: list[float] | None = None,
) -> list[dict]:
    points: list[dict] = []
    for index, (month, value) in enumerate(zip(months, values, strict=False)):
        points.append(
            {
                "period": month_label(month),
                "date": month,
                "value": quantize(value),
                "lower": quantize(lower[index]) if lower else None,
                "upper": quantize(upper[index]) if upper else None,
                "is_forecast": is_forecast,
            }
        )
    return points


def build_forecast(
    session: Session, user: User, horizon: int = DEFAULT_HORIZON, today: date | None = None
) -> dict:
    today = today or date.today()
    horizon = max(1, min(horizon, MAX_HORIZON))

    months, income_values, expense_values = _monthly_series(session, user, today)
    month_count = len(months)

    if month_count < forecasting.MIN_MONTHS_FOR_FORECAST:
        return {
            "sufficient_data": False,
            "message": forecasting.insufficient_data_message(month_count),
            "months_of_history": month_count,
            "horizon_months": horizon,
            "generated_at": datetime.now(UTC),
            "currency": user.currency,
            "income": None,
            "expense": None,
            "net_cashflow": [],
            "projected_balance": [],
            "limitations": [
                "No forecast is shown because there is not enough history to "
                "produce one honestly."
            ],
            "method_explanation": (
                "Finora selects a forecasting model based on how much history you "
                "have, and declines to forecast below three complete months."
            ),
        }

    income_result = forecasting.forecast_series(income_values, horizon)
    expense_result = forecasting.forecast_series(expense_values, horizon)
    future_months = forecasting.next_periods(months[-1], horizon)

    income_series = None
    if income_result:
        income_series = {
            "name": "Income",
            "method": income_result.method,
            "model_detail": income_result.method_detail,
            "history": _points(months, income_values),
            "forecast": _points(
                future_months,
                income_result.forecast,
                True,
                income_result.lower,
                income_result.upper,
            ),
        }

    expense_series = None
    if expense_result:
        expense_series = {
            "name": "Expenses",
            "method": expense_result.method,
            "model_detail": expense_result.method_detail,
            "history": _points(months, expense_values),
            "forecast": _points(
                future_months,
                expense_result.forecast,
                True,
                expense_result.lower,
                expense_result.upper,
            ),
        }

    # Net cash flow: historical actuals followed by forecast differences.
    net: list[dict] = []
    for month, inc, exp in zip(months, income_values, expense_values, strict=False):
        net.append(
            {
                "period": month_label(month),
                "date": month,
                "value": quantize(inc - exp),
                "lower": None,
                "upper": None,
                "is_forecast": False,
            }
        )
    if income_result and expense_result:
        for index, month in enumerate(future_months):
            point = income_result.forecast[index] - expense_result.forecast[index]
            # Worst case for net flow is low income with high expenses.
            worst = income_result.lower[index] - expense_result.upper[index]
            best = income_result.upper[index] - expense_result.lower[index]
            net.append(
                {
                    "period": month_label(month),
                    "date": month,
                    "value": quantize(point),
                    "lower": quantize(worst),
                    "upper": quantize(best),
                    "is_forecast": True,
                }
            )

    # Cumulative projected balance, anchored at zero at the start of the
    # forecast (Finora tracks flows, not bank balances - so this is the change
    # in your position, and the UI labels it that way).
    projected: list[dict] = []
    running = Decimal("0")
    running_low = Decimal("0")
    running_high = Decimal("0")
    for entry in net:
        if not entry["is_forecast"]:
            continue
        running += Decimal(str(entry["value"]))
        running_low += Decimal(str(entry["lower"]))
        running_high += Decimal(str(entry["upper"]))
        projected.append(
            {
                "period": entry["period"],
                "date": entry["date"],
                "value": quantize(running),
                "lower": quantize(running_low),
                "upper": quantize(running_high),
                "is_forecast": True,
            }
        )

    method = expense_result.method if expense_result else "unknown"
    return {
        "sufficient_data": True,
        "message": None,
        "months_of_history": month_count,
        "horizon_months": horizon,
        "generated_at": datetime.now(UTC),
        "currency": user.currency,
        "income": income_series,
        "expense": expense_series,
        "net_cashflow": net,
        "projected_balance": projected,
        "limitations": forecasting.limitations(month_count, method),
        "method_explanation": (
            "Monthly income and expense totals are aggregated from your "
            "transactions (the current, incomplete month is excluded). Finora "
            "then selects a model based on series length: Holt-Winters with "
            "seasonality at 24+ months, damped Holt's trend at 12+, simple "
            "exponential smoothing at 6+, and a weighted moving average below "
            "that. The band is an 80% prediction interval from in-sample "
            "residuals, widening with the forecast horizon."
        ),
    }


def summary_for_ai(session: Session, user: User, today: date | None = None) -> dict:
    """Compact, factual forecast summary for the AI assistant's tool layer."""
    result = build_forecast(session, user, horizon=3, today=today)
    if not result["sufficient_data"]:
        return {
            "available": False,
            "reason": result["message"],
            "months_of_history": result["months_of_history"],
        }

    expense = result["expense"]
    income = result["income"]
    return {
        "available": True,
        "months_of_history": result["months_of_history"],
        "method": expense["method"] if expense else None,
        "next_month": {
            "period": expense["forecast"][0]["period"] if expense else None,
            "projected_income": float(income["forecast"][0]["value"]) if income else None,
            "projected_expenses": float(expense["forecast"][0]["value"]) if expense else None,
            "projected_net": float(
                next(p["value"] for p in result["net_cashflow"] if p["is_forecast"])
            ),
            "expense_range": (
                [float(expense["forecast"][0]["lower"]), float(expense["forecast"][0]["upper"])]
                if expense
                else None
            ),
        },
        "caveat": (
            "This is a statistical projection from your own history with an 80% "
            "interval, not a guarantee."
        ),
    }
