"""Spending analytics.

Every figure returned here is aggregated in SQL or from ORM rows - there is no
place where a number is passed through from the client. The comparison period is
always the immediately preceding window of identical length, so a "30 days" view
compares against the 30 days before it rather than a calendar month.
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import Transaction, TransactionType, User
from app.repositories import transaction_repository as repo
from app.utils.dates import DateRange, iter_months, month_key, month_label
from app.utils.money import percent_of, percentage_change, quantize

logger = logging.getLogger(__name__)

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Recurring-expense detection thresholds.
MIN_RECURRING_OCCURRENCES = 3
# A merchant is "recurring" when the gaps between charges are consistent. 0.35
# relative deviation tolerates a monthly bill landing on the 1st vs the 4th.
MAX_INTERVAL_VARIATION = 0.35


def _expense_total(transactions: list[Transaction]) -> Decimal:
    return sum(
        (Decimal(t.amount) for t in transactions if t.type == TransactionType.EXPENSE),
        Decimal("0"),
    )


def _income_total(transactions: list[Transaction]) -> Decimal:
    return sum(
        (Decimal(t.amount) for t in transactions if t.type == TransactionType.INCOME),
        Decimal("0"),
    )


def category_breakdown(
    session: Session, user: User, period: DateRange, compare: bool = True
) -> list[dict]:
    """Expense totals per category, with change against the previous window."""
    rows = repo.sum_by_category(session, user.id, period.start, period.end)
    total = sum((row[3] for row in rows), Decimal("0"))

    previous_by_id: dict[str | None, Decimal] = {}
    if compare:
        previous = period.previous()
        previous_by_id = {
            row[0]: row[3]
            for row in repo.sum_by_category(session, user.id, previous.start, previous.end)
        }

    breakdown: list[dict] = []
    for category_id, name, color, amount, count in rows:
        previous_amount = previous_by_id.get(category_id)
        breakdown.append(
            {
                "category_id": category_id,
                "category": name,
                "color": color,
                "amount": quantize(amount),
                "percentage": percent_of(amount, total),
                "transaction_count": count,
                "average": quantize(amount / count if count else 0),
                "previous_amount": quantize(previous_amount) if compare else None,
                "change_pct": (
                    percentage_change(amount, previous_amount)
                    if compare and previous_amount is not None
                    else None
                ),
            }
        )
    return breakdown


def merchant_breakdown(
    session: Session, user: User, period: DateRange, limit: int = 12
) -> list[dict]:
    rows = repo.sum_by_merchant(session, user.id, period.start, period.end, limit)

    # Attach each merchant's dominant category for display.
    transactions = repo.list_in_range(
        session, user.id, period.start, period.end, transaction_type=TransactionType.EXPENSE
    )
    merchant_categories: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for t in transactions:
        if t.merchant and t.category:
            merchant_categories[t.merchant][t.category.name] += 1

    out: list[dict] = []
    for merchant, amount, count, last_seen in rows:
        categories = merchant_categories.get(merchant, {})
        dominant = max(categories, key=categories.get) if categories else None
        out.append(
            {
                "merchant": merchant,
                "amount": quantize(amount),
                "transaction_count": count,
                "average": quantize(amount / count if count else 0),
                "last_seen": last_seen,
                "category": dominant,
            }
        )
    return out


def daily_series(transactions: list[Transaction], period: DateRange) -> list[dict]:
    """Per-day income/expense totals, including days with no activity.

    Gaps must be explicit zeros, not missing keys: a line chart that skips empty
    days silently compresses time and misrepresents the trend.
    """
    expense_by_day: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    income_by_day: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
    count_by_day: dict[date, int] = defaultdict(int)

    for t in transactions:
        if t.type == TransactionType.EXPENSE:
            expense_by_day[t.occurred_on] += Decimal(t.amount)
            count_by_day[t.occurred_on] += 1
        elif t.type == TransactionType.INCOME:
            income_by_day[t.occurred_on] += Decimal(t.amount)

    series: list[dict] = []
    cursor = period.start
    while cursor <= period.end:
        series.append(
            {
                "date": cursor.isoformat(),
                "label": cursor.strftime("%d %b"),
                "expense": quantize(expense_by_day[cursor]),
                "income": quantize(income_by_day[cursor]),
                "transaction_count": count_by_day[cursor],
            }
        )
        cursor += timedelta(days=1)
    return series


def monthly_series(
    session: Session, user: User, months: int = 6, today: date | None = None
) -> list[dict]:
    """Income / expense / savings per month for the trailing ``months`` months."""
    today = today or date.today()
    from app.utils.dates import add_months, month_start

    start = month_start(add_months(today, -(months - 1)))
    transactions = repo.list_in_range(session, user.id, start, today)

    income: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    expense: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for t in transactions:
        key = month_key(t.occurred_on)
        if t.type == TransactionType.INCOME:
            income[key] += Decimal(t.amount)
        elif t.type == TransactionType.EXPENSE:
            expense[key] += Decimal(t.amount)

    series: list[dict] = []
    for month in iter_months(start, today):
        key = month_key(month)
        month_income = income[key]
        month_expense = expense[key]
        savings = month_income - month_expense
        series.append(
            {
                "month": key,
                "label": month_label(month),
                "income": quantize(month_income),
                "expense": quantize(month_expense),
                "savings": quantize(savings),
                "savings_rate": percent_of(savings, month_income) if month_income > 0 else 0.0,
            }
        )
    return series


def weekday_series(transactions: list[Transaction]) -> list[dict]:
    totals: dict[int, Decimal] = {i: Decimal("0") for i in range(7)}
    counts: dict[int, int] = {i: 0 for i in range(7)}
    for t in transactions:
        if t.type != TransactionType.EXPENSE:
            continue
        weekday = t.occurred_on.weekday()
        totals[weekday] += Decimal(t.amount)
        counts[weekday] += 1

    return [
        {
            "weekday": WEEKDAY_NAMES[i],
            "amount": quantize(totals[i]),
            "transaction_count": counts[i],
            "average": quantize(totals[i] / counts[i] if counts[i] else 0),
        }
        for i in range(7)
    ]


def detect_recurring(
    session: Session, user: User, today: date | None = None, lookback_days: int = 180
) -> list[dict]:
    """Find merchants charged on a consistent cadence.

    Method: group expenses by merchant, require at least three charges, then
    measure the gaps between consecutive charges. If the gaps are consistent
    (relative deviation under the threshold) the merchant is recurring, and the
    median gap determines the cadence label and the next expected date.
    """
    today = today or date.today()
    start = today - timedelta(days=lookback_days)
    transactions = repo.list_in_range(
        session, user.id, start, today, transaction_type=TransactionType.EXPENSE
    )

    by_merchant: dict[str, list[Transaction]] = defaultdict(list)
    for t in transactions:
        if t.merchant:
            by_merchant[t.merchant].append(t)

    recurring: list[dict] = []
    for merchant, items in by_merchant.items():
        if len(items) < MIN_RECURRING_OCCURRENCES:
            continue

        items.sort(key=lambda t: t.occurred_on)
        dates = [t.occurred_on for t in items]
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        gaps = [g for g in gaps if g > 0]
        if len(gaps) < 2:
            continue

        median_gap = statistics.median(gaps)
        if median_gap <= 0:
            continue
        deviation = statistics.stdev(gaps) / median_gap if len(gaps) > 1 else 0.0
        if deviation > MAX_INTERVAL_VARIATION:
            continue

        amounts = [float(t.amount) for t in items]
        cadence = _cadence_label(median_gap)
        if cadence == "irregular":
            continue

        # Confidence blends interval consistency with amount consistency: a true
        # subscription is regular in both.
        amount_mean = statistics.fmean(amounts)
        amount_cv = (
            (statistics.stdev(amounts) / amount_mean) if len(amounts) > 1 and amount_mean else 0.0
        )
        confidence = round(
            max(
                0.0,
                min(
                    1.0,
                    (1 - deviation / MAX_INTERVAL_VARIATION) * 0.6 + max(0.0, 1 - amount_cv) * 0.4,
                ),
            ),
            2,
        )

        recurring.append(
            {
                "merchant": merchant,
                "category": items[-1].category.name if items[-1].category else None,
                "occurrences": len(items),
                "average_amount": quantize(amount_mean),
                "total_amount": quantize(sum(amounts)),
                "median_interval_days": round(median_gap, 1),
                "cadence": cadence,
                "last_seen": dates[-1],
                "next_expected": dates[-1] + timedelta(days=int(median_gap)),
                "confidence": confidence,
            }
        )

    recurring.sort(key=lambda r: r["average_amount"], reverse=True)
    return recurring


def _cadence_label(days: float) -> str:
    if 5 <= days <= 9:
        return "weekly"
    if 12 <= days <= 16:
        return "fortnightly"
    if 25 <= days <= 35:
        return "monthly"
    if 85 <= days <= 95:
        return "quarterly"
    return "irregular"


def build_analytics(
    session: Session, user: User, period: DateRange, today: date | None = None
) -> dict:
    today = today or date.today()
    transactions = repo.list_in_range(session, user.id, period.start, period.end)
    previous_period = period.previous()
    previous_transactions = repo.list_in_range(
        session, user.id, previous_period.start, previous_period.end
    )

    expense_total = _expense_total(transactions)
    income_total = _income_total(transactions)
    previous_expense = _expense_total(previous_transactions)
    previous_income = _income_total(previous_transactions)

    expenses = [Decimal(t.amount) for t in transactions if t.type == TransactionType.EXPENSE]
    savings = income_total - expense_total

    stats = {
        "transaction_count": len(transactions),
        "expense_count": len(expenses),
        "average_transaction": quantize(
            sum(expenses, Decimal("0")) / len(expenses) if expenses else 0
        ),
        "median_transaction": quantize(
            statistics.median([float(e) for e in expenses]) if expenses else 0
        ),
        "largest_transaction": quantize(max(expenses) if expenses else 0),
        "smallest_transaction": quantize(min(expenses) if expenses else 0),
        "daily_average_spend": quantize(expense_total / period.days if period.days else 0),
        "active_days": len({t.occurred_on for t in transactions}),
        "distinct_merchants": len({t.merchant for t in transactions if t.merchant}),
    }

    return {
        "period": period.as_dict() | {"days": period.days},
        "comparison_period": previous_period.as_dict() | {"days": previous_period.days},
        "currency": user.currency,
        "totals": {
            "income": quantize(income_total),
            "expense": quantize(expense_total),
            "savings": quantize(savings),
            "savings_rate": percent_of(savings, income_total) if income_total > 0 else 0.0,
            "previous_income": quantize(previous_income),
            "previous_expense": quantize(previous_expense),
            "income_change_pct": percentage_change(income_total, previous_income),
            "expense_change_pct": percentage_change(expense_total, previous_expense),
        },
        "by_category": category_breakdown(session, user, period),
        "by_merchant": merchant_breakdown(session, user, period),
        "by_month": monthly_series(session, user, months=6, today=today),
        "by_day": daily_series(transactions, period),
        "by_weekday": weekday_series(transactions),
        "largest_expenses": repo.largest_expenses(session, user.id, period.start, period.end),
        "recurring": detect_recurring(session, user, today),
        "stats": stats,
        "has_data": len(transactions) > 0,
    }


def spending_for_ai(
    session: Session, user: User, period: DateRange, category_name: str | None = None
) -> dict:
    """Factual spending figures for the AI assistant's tool layer."""
    transactions = repo.list_in_range(session, user.id, period.start, period.end)
    if category_name:
        matching = [
            t
            for t in transactions
            if t.type == TransactionType.EXPENSE
            and t.category
            and t.category.name.lower() == category_name.lower()
        ]
        if not matching:
            return {
                "available": False,
                "category": category_name,
                "period": period.as_dict(),
                "reason": (
                    f"No {category_name} expenses were recorded between "
                    f"{period.start.isoformat()} and {period.end.isoformat()}."
                ),
            }
        total = sum((Decimal(t.amount) for t in matching), Decimal("0"))
        return {
            "available": True,
            "category": category_name,
            "period": period.as_dict(),
            "total": float(total),
            "transaction_count": len(matching),
            "average": float(total / len(matching)),
            "largest": float(max(Decimal(t.amount) for t in matching)),
            "top_merchants": [
                {"merchant": m, "amount": float(a)}
                for m, a, _c, _l in repo.sum_by_merchant(
                    session, user.id, period.start, period.end, limit=50
                )
                if any(t.merchant == m for t in matching)
            ][:5],
        }

    expense_total = _expense_total(transactions)
    income_total = _income_total(transactions)
    categories = category_breakdown(session, user, period, compare=False)

    return {
        "available": len(transactions) > 0,
        "period": period.as_dict(),
        "total_income": float(income_total),
        "total_expenses": float(expense_total),
        "net_savings": float(income_total - expense_total),
        "savings_rate_pct": percent_of(income_total - expense_total, income_total),
        "transaction_count": len(transactions),
        "top_categories": [
            {
                "category": c["category"],
                "amount": float(c["amount"]),
                "percentage": c["percentage"],
                "transaction_count": c["transaction_count"],
            }
            for c in categories[:6]
        ],
        "reason": None
        if transactions
        else (
            f"No transactions recorded between {period.start.isoformat()} and "
            f"{period.end.isoformat()}."
        ),
    }
