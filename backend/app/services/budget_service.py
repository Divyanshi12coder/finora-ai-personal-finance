"""Budget computation and AI budget recommendations.

Two distinct jobs:

1. **Status** - given a budget's limits, compute spent / remaining /
   utilisation / pace from the transactions table. No spend figure is ever
   stored; it is derived on every read so it cannot drift.

2. **Recommendations** - analyse historical per-category spending and propose
   realistic limits, with the statistics behind each number exposed so the user
   can judge the suggestion rather than trust it blindly.
"""

from __future__ import annotations

import logging
import statistics
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Budget, BudgetItem, Category, TransactionType, User
from app.repositories import transaction_repository as repo
from app.schemas.budget import BudgetCreate, BudgetUpdate
from app.services import category_service
from app.utils.dates import (
    add_months,
    iter_months,
    month_end,
    month_key,
    month_label,
    month_start,
    parse_month_key,
)
from app.utils.money import percent_of, quantize, to_decimal

logger = logging.getLogger(__name__)

# Utilisation bands (percent of limit consumed).
WATCH_THRESHOLD = 75.0
AT_RISK_THRESHOLD = 90.0

# Recommendation tuning.
MIN_MONTHS_FOR_RECOMMENDATION = 2
IDEAL_MONTHS = 6
# Buffer above the central estimate, by budgeting style. A budget set exactly at
# the historical mean is breached half the time by construction.
STYLE_BUFFER = {"strict": Decimal("1.02"), "balanced": Decimal("1.08"), "flexible": Decimal("1.15")}
ROUND_TO = Decimal("50")


class BudgetError(Exception):
    """Business-rule violation; routers map this to a 400."""


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------
def list_budgets(session: Session, user: User) -> list[Budget]:
    stmt = (
        select(Budget)
        .where(Budget.user_id == user.id)
        .options(joinedload(Budget.items).joinedload(BudgetItem.category))
        .order_by(Budget.period_month.desc())
    )
    return list(session.scalars(stmt).unique().all())


def get_budget(session: Session, user: User, budget_id: str) -> Budget | None:
    stmt = (
        select(Budget)
        .where(Budget.id == budget_id, Budget.user_id == user.id)
        .options(joinedload(Budget.items).joinedload(BudgetItem.category))
    )
    return session.scalars(stmt).unique().first()


def get_budget_for_month(session: Session, user: User, month: date) -> Budget | None:
    stmt = (
        select(Budget)
        .where(Budget.user_id == user.id, Budget.period_month == month_start(month))
        .options(joinedload(Budget.items).joinedload(BudgetItem.category))
    )
    return session.scalars(stmt).unique().first()


def create_budget(session: Session, user: User, payload: BudgetCreate) -> Budget:
    period = parse_month_key(payload.period_month)

    if get_budget_for_month(session, user, period) is not None:
        raise BudgetError(f"A budget already exists for {month_label(period)}. Edit it instead.")

    budget = Budget(
        user_id=user.id,
        name=payload.name,
        period_month=period,
        total_limit=payload.total_limit,
        notes=payload.notes,
    )
    session.add(budget)
    session.flush()
    _replace_items(session, user, budget, payload.items)
    session.flush()
    return budget


def update_budget(session: Session, user: User, budget: Budget, payload: BudgetUpdate) -> Budget:
    data = payload.model_dump(exclude_unset=True)
    items = data.pop("items", None)

    for field, value in data.items():
        setattr(budget, field, value)

    if items is not None:
        _replace_items(session, user, budget, payload.items or [])

    session.flush()
    return budget


def _replace_items(session: Session, user: User, budget: Budget, items) -> None:
    """Replace the budget's line items, validating category ownership."""
    for existing in list(budget.items):
        session.delete(existing)
    session.flush()

    seen: set[str] = set()
    for item in items or []:
        if item.category_id in seen:
            raise BudgetError("A category can only appear once in a budget")
        category = category_service.get_category_for_user(session, user, item.category_id)
        if category is None:
            raise BudgetError(f"Category {item.category_id} not found or not accessible")
        seen.add(item.category_id)
        session.add(
            BudgetItem(
                budget_id=budget.id,
                category_id=category.id,
                limit_amount=item.limit_amount,
            )
        )
    session.flush()
    session.refresh(budget)


def delete_budget(session: Session, budget: Budget) -> None:
    session.delete(budget)
    session.flush()


# --------------------------------------------------------------------------
# Status computation
# --------------------------------------------------------------------------
def _classify(utilization: float, expected: float) -> str:
    # Strictly greater than 100: spending exactly to the limit is using the
    # budget as intended, not breaching it. Reporting "exceeded by ₹0" would be
    # both wrong and nonsense to read.
    if utilization > 100:
        return "exceeded"
    if utilization >= AT_RISK_THRESHOLD:
        return "at_risk"
    # Meaningfully ahead of a linear pace is worth a nudge even below 90%.
    if utilization >= WATCH_THRESHOLD or utilization > expected + 15:
        return "watch"
    return "on_track"


def compute_status(session: Session, user: User, budget: Budget, today: date | None = None) -> dict:
    """Derive every spend figure for a budget from the transactions table."""
    today = today or date.today()
    period_start = budget.period_month
    period_end = month_end(period_start)

    days_total = (period_end - period_start).days + 1
    if today < period_start:
        days_elapsed = 0
    elif today > period_end:
        days_elapsed = days_total
    else:
        days_elapsed = (today - period_start).days + 1
    days_remaining = max(0, days_total - days_elapsed)
    expected_utilization = round(days_elapsed / days_total * 100, 2) if days_total else 0.0

    items_out: list[dict] = []
    warnings: list[str] = []
    allocated = Decimal("0")

    for item in budget.items:
        spent, count = repo.sum_for_category(
            session, user.id, item.category_id, period_start, period_end
        )
        limit = to_decimal(item.limit_amount)
        allocated += limit
        remaining = limit - spent
        utilization = percent_of(spent, limit)
        daily_average = spent / days_elapsed if days_elapsed else Decimal("0")
        projected = daily_average * days_total
        projected_overspend = max(Decimal("0"), projected - limit)
        status = _classify(utilization, expected_utilization)

        warning = _build_warning(
            category_name=item.category.name,
            utilization=utilization,
            days_remaining=days_remaining,
            remaining=remaining,
            projected_overspend=projected_overspend,
            status=status,
            is_current_month=period_start <= today <= period_end,
        )
        if warning:
            warnings.append(warning)

        items_out.append(
            {
                "id": item.id,
                "category": item.category,
                "limit_amount": quantize(limit),
                "spent": quantize(spent),
                "remaining": quantize(remaining),
                "utilization": utilization,
                "status": status,
                "transaction_count": count,
                "daily_average": quantize(daily_average),
                "projected_spend": quantize(projected),
                "projected_overspend": quantize(projected_overspend),
                "recommended_amount": (
                    quantize(item.recommended_amount) if item.recommended_amount else None
                ),
                "recommendation_basis": item.recommendation_basis,
                "warning": warning,
            }
        )

    items_out.sort(key=lambda i: i["utilization"], reverse=True)

    # Overall spend covers the whole month, including categories with no limit -
    # otherwise the headline number would understate what the user actually spent.
    totals = repo.sum_by_type(session, user.id, period_start, period_end)
    total_spent = totals.get(TransactionType.EXPENSE.value, Decimal("0"))
    effective_limit = to_decimal(budget.total_limit) if budget.total_limit else allocated
    total_utilization = percent_of(total_spent, effective_limit)

    return {
        "id": budget.id,
        "name": budget.name,
        "period_month": budget.period_month,
        "period_label": month_label(budget.period_month),
        "total_limit": quantize(budget.total_limit) if budget.total_limit else None,
        "notes": budget.notes,
        "allocated": quantize(allocated),
        "spent": quantize(total_spent),
        "remaining": quantize(effective_limit - total_spent),
        "utilization": total_utilization,
        "days_total": days_total,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "expected_utilization": expected_utilization,
        "status": _classify(total_utilization, expected_utilization),
        "items": items_out,
        "warnings": warnings,
    }


def _build_warning(
    category_name: str,
    utilization: float,
    days_remaining: int,
    remaining: Decimal,
    projected_overspend: Decimal,
    status: str,
    is_current_month: bool,
) -> str | None:
    """Produce the concrete, numeric warning shown on the budget card."""
    if not is_current_month:
        if status == "exceeded":
            return f"{category_name} finished {utilization - 100:.0f}% over its limit."
        return None

    day_word = "day" if days_remaining == 1 else "days"

    if status == "exceeded":
        return (
            f"You've exceeded your {category_name} budget by ₹{abs(remaining):,.0f} "
            f"with {days_remaining} {day_word} left in the month."
        )
    if status == "at_risk":
        if remaining <= 0:
            return (
                f"Your {category_name} budget is fully used with {days_remaining} "
                f"{day_word} left in the month."
            )
        return (
            f"You're {utilization:.0f}% through your {category_name} budget with "
            f"{days_remaining} {day_word} remaining - ₹{remaining:,.0f} left."
        )
    if status == "watch":
        if projected_overspend > 0:
            return (
                f"At your current pace, {category_name} is on track to finish "
                f"₹{projected_overspend:,.0f} over budget."
            )
        return (
            f"{category_name} is at {utilization:.0f}% with {days_remaining} " f"{day_word} to go."
        )
    return None


def current_month_summary(session: Session, user: User, today: date | None = None) -> dict | None:
    today = today or date.today()
    budget = get_budget_for_month(session, user, today)
    if budget is None:
        return None
    return compute_status(session, user, budget, today)


# --------------------------------------------------------------------------
# Recommendations
# --------------------------------------------------------------------------
def _trimmed_mean(values: list[float]) -> float:
    """Mean after dropping the single highest value when there are >= 4 months.

    One festive month or one annual premium should inform the buffer, not the
    central estimate.
    """
    if len(values) >= 4:
        trimmed = sorted(values)[:-1]
        return statistics.fmean(trimmed)
    return statistics.fmean(values)


def _round_up(value: Decimal) -> Decimal:
    """Round to a human number - nobody budgets ₹9,473."""
    if value <= 0:
        return Decimal("0")
    return (value / ROUND_TO).to_integral_value(rounding="ROUND_CEILING") * ROUND_TO


def recommend_budgets(
    session: Session,
    user: User,
    period_month: str | None = None,
    today: date | None = None,
) -> dict:
    """Recommend per-category limits from the user's own spending history."""
    today = today or date.today()
    target_month = parse_month_key(period_month) if period_month else month_start(today)

    # Analyse complete months only, ending with the month before the target.
    analysis_end = month_end(add_months(target_month, -1))
    analysis_start = month_start(add_months(target_month, -IDEAL_MONTHS))

    transactions = repo.list_in_range(
        session,
        user.id,
        analysis_start,
        analysis_end,
        transaction_type=TransactionType.EXPENSE,
    )

    months = list(iter_months(analysis_start, analysis_end))
    # Only count months in which the user actually recorded something.
    active_months = sorted({month_key(t.occurred_on) for t in transactions})
    months_analyzed = len(active_months)

    if months_analyzed < MIN_MONTHS_FOR_RECOMMENDATION:
        return {
            "period_month": month_key(target_month),
            "generated_at": datetime.now(UTC).isoformat(),
            "months_analyzed": months_analyzed,
            "sufficient_data": False,
            "message": (
                f"Budget recommendations are based on your spending history. "
                f"You have {months_analyzed} month(s) of complete data; at least "
                f"{MIN_MONTHS_FOR_RECOMMENDATION} are needed before Finora will "
                "suggest a number. Until then, set limits manually."
            ),
            "total_recommended": Decimal("0"),
            "items": [],
            "methodology": methodology_text(),
        }

    # Per-category, per-month totals.
    by_category: dict[str, dict[str, Decimal]] = {}
    category_objects: dict[str, Category] = {}
    for t in transactions:
        if t.category is None:
            continue
        key = t.category.id
        category_objects[key] = t.category
        by_category.setdefault(key, {})
        month = month_key(t.occurred_on)
        by_category[key][month] = by_category[key].get(month, Decimal("0")) + Decimal(t.amount)

    existing = get_budget_for_month(session, user, target_month)
    existing_limits = (
        {item.category_id: to_decimal(item.limit_amount) for item in existing.items}
        if existing
        else {}
    )

    buffer = STYLE_BUFFER.get(user.budgeting_preference.value, Decimal("1.08"))
    items: list[dict] = []
    total = Decimal("0")

    for category_id, monthly in by_category.items():
        category = category_objects[category_id]
        # Months where the category saw no spend count as zero, otherwise a
        # category bought twice a year looks like a monthly commitment.
        series = [float(monthly.get(month_key(m), Decimal("0"))) for m in months]
        # Trim leading zeros before the user started recording at all.
        first_nonzero = next((i for i, v in enumerate(series) if v > 0), None)
        if first_nonzero is None:
            continue
        series = series[first_nonzero:]
        if len(series) < MIN_MONTHS_FOR_RECOMMENDATION:
            continue

        mean = statistics.fmean(series)
        median = statistics.median(series)
        std_dev = statistics.stdev(series) if len(series) > 1 else 0.0
        central = _trimmed_mean(series)

        # Trend: compare the most recent month against the mean of the earlier
        # ones. A rising category should not be budgeted at its old average.
        trend_pct: float | None = None
        if len(series) >= 3:
            earlier = statistics.fmean(series[:-1])
            if earlier > 0:
                trend_pct = round((series[-1] - earlier) / earlier * 100, 1)

        base = Decimal(str(central))
        # If spending is clearly trending up, nudge the central estimate toward
        # the latest month rather than anchoring on a stale average.
        if trend_pct is not None and trend_pct > 15:
            base = (base + Decimal(str(series[-1]))) / 2

        recommended = _round_up(base * buffer)
        total += recommended

        confidence = (
            "high"
            if len(series) >= 5 and std_dev <= mean * 0.3
            else "medium"
            if len(series) >= 3
            else "low"
        )

        rationale = _rationale(
            category.name,
            series,
            central,
            recommended,
            trend_pct,
            std_dev,
            mean,
            user.budgeting_preference.value,
        )

        items.append(
            {
                "category_id": category_id,
                "category_name": category.name,
                "recommended_amount": quantize(recommended),
                "current_limit": (
                    quantize(existing_limits[category_id])
                    if category_id in existing_limits
                    else None
                ),
                "method": "trimmed_mean_plus_style_buffer",
                "confidence": confidence,
                "months_analyzed": len(series),
                "monthly_history": [
                    {"month": month_label(m), "amount": float(monthly.get(month_key(m), 0))}
                    for m in months[first_nonzero:]
                ],
                "mean": quantize(mean),
                "median": quantize(median),
                "std_dev": quantize(std_dev),
                "trend_pct": trend_pct,
                "rationale": rationale,
            }
        )

    items.sort(key=lambda i: i["recommended_amount"], reverse=True)

    return {
        "period_month": month_key(target_month),
        "generated_at": datetime.now(UTC).isoformat(),
        "months_analyzed": months_analyzed,
        "sufficient_data": True,
        "message": None,
        "total_recommended": quantize(total),
        "items": items,
        "methodology": methodology_text(),
    }


def _rationale(
    name: str,
    series: list[float],
    central: float,
    recommended: Decimal,
    trend_pct: float | None,
    std_dev: float,
    mean: float,
    style: str,
) -> str:
    history = " -> ".join(f"₹{v:,.0f}" for v in series)
    parts = [f"Your last {len(series)} months of {name} spending: {history}."]

    if len(series) >= 4:
        parts.append(
            f"Excluding the single highest month, your typical spend is " f"₹{central:,.0f}."
        )
    else:
        parts.append(f"Your average is ₹{central:,.0f}.")

    if trend_pct is not None and trend_pct > 15:
        parts.append(
            f"The most recent month is {trend_pct:.0f}% above your earlier average, "
            "so the estimate is weighted toward it rather than the older figure."
        )
    elif trend_pct is not None and trend_pct < -15:
        parts.append(
            f"The most recent month is {abs(trend_pct):.0f}% below your earlier "
            "average - if that is deliberate, you could set this lower."
        )

    variability = std_dev / mean if mean > 0 else 0
    if variability > 0.35:
        parts.append(
            f"This category varies a lot month to month (±₹{std_dev:,.0f}), so "
            "treat the number as a guide rather than a hard ceiling."
        )

    parts.append(
        f"A {style} buffer is applied on top and the result is rounded, giving "
        f"₹{recommended:,.0f}."
    )
    return " ".join(parts)


def methodology_text() -> str:
    return (
        "Recommendations are computed from your own transaction history, not from "
        "generic benchmarks. For each category Finora builds a monthly spend "
        "series over the last six complete months, takes a trimmed mean (dropping "
        "the single highest month once four or more months exist) as the central "
        "estimate, checks whether the latest month is trending more than 15% away "
        "from the earlier average and re-weights toward it if so, applies a buffer "
        "based on your budgeting style (strict 2%, balanced 8%, flexible 15%), and "
        "rounds up to the nearest ₹50. The full monthly series, mean, median and "
        "standard deviation behind every suggestion are returned alongside it."
    )


def apply_recommendations(
    session: Session,
    user: User,
    period_month: str,
    category_ids: list[str] | None = None,
    today: date | None = None,
) -> Budget:
    """Create or update a budget using the recommended limits."""
    recommendations = recommend_budgets(session, user, period_month, today)
    if not recommendations["sufficient_data"]:
        raise BudgetError(recommendations["message"])

    selected = [
        item
        for item in recommendations["items"]
        if category_ids is None or item["category_id"] in category_ids
    ]
    if not selected:
        raise BudgetError("No recommendations available for the selected categories")

    period = parse_month_key(period_month)
    budget = get_budget_for_month(session, user, period)
    if budget is None:
        budget = Budget(
            user_id=user.id,
            name=f"{month_label(period)} budget",
            period_month=period,
            total_limit=sum((i["recommended_amount"] for i in selected), Decimal("0")),
        )
        session.add(budget)
        session.flush()

    existing_by_category = {item.category_id: item for item in budget.items}
    for item in selected:
        row = existing_by_category.get(item["category_id"])
        if row is None:
            row = BudgetItem(
                budget_id=budget.id,
                category_id=item["category_id"],
                limit_amount=item["recommended_amount"],
            )
            session.add(row)
        else:
            row.limit_amount = item["recommended_amount"]
        row.recommended_amount = item["recommended_amount"]
        row.recommendation_basis = item["rationale"]

    session.flush()
    session.refresh(budget)
    logger.info(
        "Applied %d budget recommendations for user %s (%s)",
        len(selected),
        user.id,
        period_month,
    )
    return budget


def status_for_ai(session: Session, user: User, today: date | None = None) -> dict:
    """Compact budget facts for the AI assistant."""
    today = today or date.today()
    summary = current_month_summary(session, user, today)
    if summary is None:
        return {
            "available": False,
            "reason": f"No budget has been set for {month_label(today)}.",
        }
    return {
        "available": True,
        "period": summary["period_label"],
        "total_limit": float(summary["total_limit"] or summary["allocated"]),
        "spent": float(summary["spent"]),
        "remaining": float(summary["remaining"]),
        "utilization_pct": summary["utilization"],
        "days_remaining": summary["days_remaining"],
        "expected_utilization_pct": summary["expected_utilization"],
        "categories": [
            {
                "category": item["category"].name,
                "limit": float(item["limit_amount"]),
                "spent": float(item["spent"]),
                "remaining": float(item["remaining"]),
                "utilization_pct": item["utilization"],
                "status": item["status"],
            }
            for item in summary["items"]
        ],
        "warnings": summary["warnings"],
    }
