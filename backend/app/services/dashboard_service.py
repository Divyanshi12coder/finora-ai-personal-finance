"""Dashboard assembly.

One endpoint composes the whole landing view so the client makes a single
request rather than six. Every figure is computed by the services below; the
dashboard only arranges them.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import TransactionType, User
from app.repositories import transaction_repository as repo
from app.services import (
    analytics_service,
    anomaly_service,
    budget_service,
    goal_service,
    health_service,
    insight_service,
)
from app.utils.dates import DateRange, add_months, month_end, month_start
from app.utils.money import percent_of, percentage_change, quantize, to_decimal

logger = logging.getLogger(__name__)


def _trend(change_pct: float | None) -> str:
    if change_pct is None:
        return "flat"
    if change_pct > 0.5:
        return "up"
    if change_pct < -0.5:
        return "down"
    return "flat"


def _metric(
    key: str,
    label: str,
    value: Decimal,
    previous: Decimal | None,
    direction_is_good: bool | None,
    unit: str = "currency",
    hint: str | None = None,
) -> dict:
    change = percentage_change(value, previous) if previous is not None else None
    return {
        "key": key,
        "label": label,
        "value": quantize(value),
        "previous_value": quantize(previous) if previous is not None else None,
        "change_pct": change,
        "trend": _trend(change),
        "direction_is_good": direction_is_good,
        "unit": unit,
        "hint": hint,
    }


def _budget_summary_payload(summary: dict | None) -> dict | None:
    """Flatten the budget status for the dashboard.

    ``budget_service.compute_status`` returns Category ORM objects on each item
    (the budget page validates those through ``BudgetItemStatus``). The dashboard
    field is a plain dict, so the categories are flattened to primitives here
    rather than being handed to the serialiser as ORM instances.
    """
    if summary is None:
        return None

    return {
        "id": summary["id"],
        "name": summary["name"],
        "period_label": summary["period_label"],
        "spent": summary["spent"],
        "allocated": summary["allocated"],
        "total_limit": summary["total_limit"],
        "remaining": summary["remaining"],
        "utilization": summary["utilization"],
        "expected_utilization": summary["expected_utilization"],
        "days_remaining": summary["days_remaining"],
        "status": summary["status"],
        "warnings": summary["warnings"][:3],
        "top_categories": [
            {
                "id": item["id"],
                "category": item["category"].name,
                "category_id": item["category"].id,
                "color": item["category"].color,
                "icon": item["category"].icon,
                "limit_amount": item["limit_amount"],
                "spent": item["spent"],
                "remaining": item["remaining"],
                "utilization": item["utilization"],
                "status": item["status"],
                "warning": item["warning"],
            }
            for item in summary["items"][:4]
        ],
    }


def build_dashboard(session: Session, user: User, today: date | None = None) -> dict:
    today = today or date.today()

    this_month = month_start(today)
    current = DateRange(start=this_month, end=today)

    # Compare against the same number of elapsed days last month, so the
    # headline percentages are meaningful on the 3rd of the month.
    last_month_start = month_start(add_months(this_month, -1))
    elapsed = today - this_month
    previous = DateRange(
        start=last_month_start,
        end=min(month_end(last_month_start), last_month_start + elapsed),
    )

    current_totals = repo.sum_by_type(session, user.id, current.start, current.end)
    previous_totals = repo.sum_by_type(session, user.id, previous.start, previous.end)

    income = current_totals.get(TransactionType.INCOME.value, Decimal("0"))
    expense = current_totals.get(TransactionType.EXPENSE.value, Decimal("0"))
    previous_income = previous_totals.get(TransactionType.INCOME.value, Decimal("0"))
    previous_expense = previous_totals.get(TransactionType.EXPENSE.value, Decimal("0"))

    savings = income - expense
    previous_savings = previous_income - previous_expense

    # "Total balance" is the net position across everything recorded, which is
    # what Finora can actually know - it does not connect to bank accounts, and
    # the UI labels it accordingly.
    earliest = repo.earliest_date(session, user.id)
    lifetime = repo.sum_by_type(session, user.id, earliest, today) if earliest else {}
    net_position = lifetime.get(TransactionType.INCOME.value, Decimal("0")) - lifetime.get(
        TransactionType.EXPENSE.value, Decimal("0")
    )

    savings_rate = percent_of(savings, income) if income > 0 else 0.0
    previous_savings_rate = (
        percent_of(previous_savings, previous_income) if previous_income > 0 else 0.0
    )

    budget_summary = budget_service.current_month_summary(session, user, today)
    budget_remaining = to_decimal(budget_summary["remaining"]) if budget_summary else Decimal("0")

    metrics = [
        _metric(
            "net_position",
            "Net Position",
            net_position,
            None,
            True,
            hint="Total recorded income minus expenses since you started using Finora",
        ),
        _metric(
            "monthly_income",
            "Monthly Income",
            income,
            previous_income,
            True,
            hint="Income recorded this month so far",
        ),
        _metric(
            "monthly_expenses",
            "Monthly Expenses",
            expense,
            previous_expense,
            False,
            hint="Expenses recorded this month so far",
        ),
        _metric(
            "savings",
            "Savings",
            savings,
            previous_savings,
            True,
            hint="Income minus expenses this month",
        ),
        _metric(
            "savings_rate",
            "Savings Rate",
            Decimal(str(savings_rate)),
            Decimal(str(previous_savings_rate)),
            True,
            unit="percent",
            hint="Share of this month's income you have kept",
        ),
        _metric(
            "budget_remaining",
            "Budget Remaining",
            budget_remaining,
            None,
            True,
            unit="currency",
            hint=(
                f"{budget_summary['days_remaining']} days left in the budget period"
                if budget_summary
                else "No budget set for this month"
            ),
        ),
    ]

    transactions = repo.list_in_range(session, user.id, current.start, current.end)
    monthly_trend = analytics_service.monthly_series(session, user, months=6, today=today)

    income_vs_expense = [
        {
            "month": row["month"],
            "label": row["label"],
            "income": row["income"],
            "expense": row["expense"],
            "savings": row["savings"],
        }
        for row in monthly_trend
    ]

    health = health_service.compute_health_score(session, user, today)
    insights = insight_service.top_insights(session, user, limit=3)

    return {
        "period": current.as_dict()
        | {
            "label": this_month.strftime("%B %Y"),
            "days_elapsed": elapsed.days + 1,
        },
        "currency": user.currency,
        "metrics": metrics,
        "income_vs_expense": income_vs_expense,
        "category_breakdown": analytics_service.category_breakdown(session, user, current),
        "daily_spending": analytics_service.daily_series(transactions, current),
        "monthly_trend": monthly_trend,
        "recent_transactions": repo.recent(session, user.id, limit=6),
        "budget_summary": _budget_summary_payload(budget_summary),
        "goal_summary": goal_service.summary(session, user, today),
        "health_score": {
            "score": health["score"],
            "grade": health["grade"],
            "band": health["band"],
            "components": health["components"],
            "has_data": health["has_data"],
        },
        "top_insights": insights,
        "anomaly_count": anomaly_service.count_flagged(session, user),
        "has_data": repo.count_all(session, user.id) > 0,
    }
