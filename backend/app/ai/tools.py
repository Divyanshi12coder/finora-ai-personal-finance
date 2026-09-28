"""The assistant's financial data-retrieval tools.

This is the mechanism that keeps the AI honest. Each tool is a plain Python
function that queries the database through the existing service layer and
returns structured facts. The assistant selects tools from the user's question,
runs them, and only then asks the model to phrase the results.

The model never sees the database, never receives another user's data (every
tool takes the authenticated ``user``), and is never asked to compute a figure.
If a tool reports ``available: False`` the assistant says the data is missing
rather than filling the gap.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from app.models import User
from app.repositories import transaction_repository as repo
from app.services import (
    analytics_service,
    budget_service,
    category_service,
    forecasting_service,
    goal_service,
    health_service,
    insight_service,
)
from app.utils.dates import DateRange, add_months, month_end, month_start, resolve_range

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    name: str
    arguments: dict
    data: dict
    summary: str


# --------------------------------------------------------------------------
# Period parsing
# --------------------------------------------------------------------------
_MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def parse_period(question: str, today: date | None = None) -> tuple[DateRange, str]:
    """Infer the period a question refers to. Returns ``(range, label)``."""
    today = today or date.today()
    text = question.lower()

    if "last month" in text or "previous month" in text:
        start = month_start(add_months(today, -1))
        return DateRange(start=start, end=month_end(start)), "last month"
    if "this year" in text or "year to date" in text or "ytd" in text:
        return DateRange(start=date(today.year, 1, 1), end=today), "this year"
    if "last year" in text:
        return DateRange(
            start=date(today.year - 1, 1, 1), end=date(today.year - 1, 12, 31)
        ), "last year"
    if "last week" in text or "past week" in text:
        return resolve_range("7d", today=today), "the last 7 days"
    if "last 3 months" in text or "past 3 months" in text or "quarter" in text:
        return resolve_range("3m", today=today), "the last 3 months"
    if "last 6 months" in text or "past 6 months" in text:
        return resolve_range("6m", today=today), "the last 6 months"
    if "last 30 days" in text or "past 30 days" in text:
        return resolve_range("30d", today=today), "the last 30 days"

    # A named month: "in August", "for September 2026"
    for name, number in _MONTH_NAMES.items():
        if re.search(rf"\b{name}\b", text):
            year_match = re.search(r"\b(20\d{2})\b", text)
            year = int(year_match.group(1)) if year_match else today.year
            # A named month later than today with no year means last year.
            if year == today.year and number > today.month:
                year -= 1
            start = date(year, number, 1)
            end = (
                min(month_end(start), today)
                if (year, number) == (today.year, today.month)
                else month_end(start)
            )
            return DateRange(start=start, end=end), start.strftime("%B %Y")

    # Default: the current month to date, which is what "this month" means and
    # what an unqualified question almost always intends.
    return DateRange(start=month_start(today), end=today), "this month"


def extract_category(session: Session, user: User, question: str) -> str | None:
    """Find a category name mentioned in the question."""
    text = question.lower()
    names = [c.name for c in category_service.list_categories(session, user)]
    # Longest first so "Food" does not shadow a custom "Food Delivery".
    for name in sorted(names, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name.lower())}\b", text):
            return name

    # Common synonyms users actually type.
    synonyms = {
        "dining": "Food",
        "restaurant": "Food",
        "restaurants": "Food",
        "eating out": "Food",
        "groceries": "Food",
        "grocery": "Food",
        "food delivery": "Food",
        "swiggy": "Food",
        "zomato": "Food",
        "travel": "Travel",
        "flights": "Travel",
        "trip": "Travel",
        "cab": "Transport",
        "cabs": "Transport",
        "uber": "Transport",
        "fuel": "Transport",
        "petrol": "Transport",
        "commute": "Transport",
        "clothes": "Shopping",
        "clothing": "Shopping",
        "amazon": "Shopping",
        "subscriptions": "Entertainment",
        "streaming": "Entertainment",
        "netflix": "Entertainment",
        "movies": "Entertainment",
        "utilities": "Bills",
        "electricity": "Bills",
        "internet": "Bills",
        "medical": "Healthcare",
        "doctor": "Healthcare",
        "medicine": "Healthcare",
        "gym": "Healthcare",
        "courses": "Education",
        "tuition": "Education",
        "salary": "Salary",
        "income": "Salary",
        "investment": "Investments",
        "sip": "Investments",
        "mutual fund": "Investments",
        "housing": "Rent",
    }
    for synonym, category in synonyms.items():
        if re.search(rf"\b{re.escape(synonym)}\b", text) and category in names:
            return category
    return None


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------
def get_monthly_spending(
    session: Session, user: User, period: DateRange, label: str = "", **_: Any
) -> ToolResult:
    data = analytics_service.spending_for_ai(session, user, period)
    if not data["available"]:
        summary = data.get("reason") or "No transactions in the requested period."
    else:
        summary = (
            f"{label or 'Period'}: income ₹{data['total_income']:,.0f}, expenses "
            f"₹{data['total_expenses']:,.0f}, net ₹{data['net_savings']:,.0f} "
            f"({data['savings_rate_pct']:.1f}% savings rate) across "
            f"{data['transaction_count']} transactions."
        )
    return ToolResult("get_monthly_spending", {"period": period.as_dict()}, data, summary)


def get_category_spending(
    session: Session,
    user: User,
    period: DateRange,
    category: str | None = None,
    label: str = "",
    **_: Any,
) -> ToolResult:
    data = analytics_service.spending_for_ai(session, user, period, category_name=category)
    if category and not data["available"]:
        summary = data.get("reason", f"No {category} spending found.")
    elif category:
        summary = (
            f"{category} in {label or 'the period'}: ₹{data['total']:,.0f} across "
            f"{data['transaction_count']} transactions "
            f"(average ₹{data['average']:,.0f}, largest ₹{data['largest']:,.0f})."
        )
    else:
        top = data.get("top_categories") or []
        if not top:
            summary = data.get("reason") or "No categorised spending in this period."
        else:
            summary = f"Top categories in {label or 'the period'}: " + ", ".join(
                f"{c['category']} ₹{c['amount']:,.0f} ({c['percentage']:.0f}%)" for c in top[:5]
            )
    return ToolResult(
        "get_category_spending",
        {"category": category, "period": period.as_dict()},
        data,
        summary,
    )


def get_recent_transactions(session: Session, user: User, limit: int = 10, **_: Any) -> ToolResult:
    transactions = repo.recent(session, user.id, limit=limit)
    data = {
        "available": bool(transactions),
        "transactions": [
            {
                "date": t.occurred_on.isoformat(),
                "merchant": t.merchant,
                "amount": float(t.amount),
                "type": t.type.value,
                "category": t.category.name if t.category else "Uncategorised",
                "payment_method": t.payment_method,
            }
            for t in transactions
        ],
        "reason": None if transactions else "No transactions recorded yet.",
    }
    summary = (
        f"{len(transactions)} most recent transactions retrieved."
        if transactions
        else "No transactions recorded yet."
    )
    return ToolResult("get_recent_transactions", {"limit": limit}, data, summary)


def get_budget_status(session: Session, user: User, **_: Any) -> ToolResult:
    data = budget_service.status_for_ai(session, user)
    if not data["available"]:
        summary = data["reason"]
    else:
        summary = (
            f"Budget for {data['period']}: ₹{data['spent']:,.0f} spent of "
            f"₹{data['total_limit']:,.0f} ({data['utilization_pct']:.0f}% used, "
            f"{data['days_remaining']} days left)."
        )
    return ToolResult("get_budget_status", {}, data, summary)


def get_goal_progress(session: Session, user: User, **_: Any) -> ToolResult:
    data = goal_service.progress_for_ai(session, user)
    if not data["available"]:
        summary = data["reason"]
    else:
        summary = f"{len(data['goals'])} goal(s): " + ", ".join(
            f"{g['name']} {g['progress_pct']:.0f}% (₹{g['saved']:,.0f}/₹{g['target']:,.0f})"
            for g in data["goals"][:4]
        )
    return ToolResult("get_goal_progress", {}, data, summary)


def get_financial_health(session: Session, user: User, **_: Any) -> ToolResult:
    data = health_service.score_for_ai(session, user)
    summary = (
        f"Financial health score {data['score']:.0f}/100 (grade {data['grade']}, "
        f"{data['band']})."
        if data["available"]
        else data["reason"]
    )
    return ToolResult("get_financial_health", {}, data, summary)


def get_forecast(session: Session, user: User, **_: Any) -> ToolResult:
    data = forecasting_service.summary_for_ai(session, user)
    if not data["available"]:
        summary = data["reason"]
    else:
        nxt = data["next_month"]
        summary = (
            f"{nxt['period']} projection: income ₹{nxt['projected_income']:,.0f}, "
            f"expenses ₹{nxt['projected_expenses']:,.0f}, net "
            f"₹{nxt['projected_net']:,.0f} (method: {data['method']})."
        )
    return ToolResult("get_forecast", {}, data, summary)


def get_insights(session: Session, user: User, **_: Any) -> ToolResult:
    data = insight_service.insights_for_ai(session, user)
    summary = (
        f"{len(data['insights'])} current insight(s): "
        + "; ".join(i["title"] for i in data["insights"][:4])
        if data["available"]
        else data["reason"]
    )
    return ToolResult("get_insights", {}, data, summary)


def get_top_merchants(
    session: Session, user: User, period: DateRange, label: str = "", **_: Any
) -> ToolResult:
    merchants = analytics_service.merchant_breakdown(session, user, period, limit=8)
    data = {
        "available": bool(merchants),
        "period": period.as_dict(),
        "merchants": [
            {
                "merchant": m["merchant"],
                "amount": float(m["amount"]),
                "transaction_count": m["transaction_count"],
                "category": m["category"],
            }
            for m in merchants
        ],
        "reason": None
        if merchants
        else f"No merchant spending recorded in {label or 'this period'}.",
    }
    summary = (
        f"Top merchants in {label or 'the period'}: "
        + ", ".join(f"{m['merchant']} ₹{m['amount']:,.0f}" for m in merchants[:5])
        if merchants
        else data["reason"]
    )
    return ToolResult("get_top_merchants", {"period": period.as_dict()}, data, summary)


def get_savings_simulation(
    session: Session,
    user: User,
    period: DateRange,
    category: str | None = None,
    reduction_pct: float = 20.0,
    label: str = "",
    **_: Any,
) -> ToolResult:
    """Compute what reducing a category by N% would actually save.

    The arithmetic is done here, in Python, against real figures - not by the
    language model.
    """
    data = analytics_service.spending_for_ai(session, user, period, category_name=category)
    if not data["available"]:
        return ToolResult(
            "get_savings_simulation",
            {"category": category, "reduction_pct": reduction_pct},
            data,
            data.get("reason", "Not enough data to simulate a reduction."),
        )

    current = data["total"] if category else data["total_expenses"]
    saving = current * (reduction_pct / 100)
    months = max(1, round((period.end - period.start).days / 30))
    monthly_saving = saving / months

    result = {
        "available": True,
        "category": category or "total expenses",
        "period": period.as_dict(),
        "current_spend": current,
        "reduction_pct": reduction_pct,
        "saving_over_period": round(saving, 2),
        "estimated_monthly_saving": round(monthly_saving, 2),
        "estimated_annual_saving": round(monthly_saving * 12, 2),
        "months_in_period": months,
    }
    summary = (
        f"Reducing {result['category']} by {reduction_pct:.0f}% would save about "
        f"₹{monthly_saving:,.0f}/month (₹{monthly_saving * 12:,.0f}/year), based on "
        f"₹{current:,.0f} spent in {label or 'the period'}."
    )
    return ToolResult(
        "get_savings_simulation",
        {"category": category, "reduction_pct": reduction_pct},
        result,
        summary,
    )


def get_goal_requirement(session: Session, user: User, question: str = "", **_: Any) -> ToolResult:
    """How much per month is needed for the goal the question mentions."""
    goals = goal_service.list_goals(session, user)
    if not goals:
        data = {"available": False, "reason": "No financial goals have been created yet."}
        return ToolResult("get_goal_requirement", {}, data, data["reason"])

    text = question.lower()
    matched = next((g for g in goals if g.name.lower() in text), None)
    if matched is None:
        # Fall back to a keyword overlap with any goal name.
        for goal in goals:
            words = [w for w in re.split(r"\W+", goal.name.lower()) if len(w) > 3]
            if any(word in text for word in words):
                matched = goal
                break
    if matched is None:
        matched = goals[0]

    enriched = goal_service.enrich(matched)
    data = {
        "available": True,
        "goal": matched.name,
        "target_amount": float(matched.target_amount),
        "current_amount": float(matched.current_amount),
        "remaining": float(enriched["remaining"]),
        "target_date": matched.target_date.isoformat() if matched.target_date else None,
        "months_remaining": enriched["months_remaining"],
        "required_monthly": (
            float(enriched["suggested_monthly_contribution"])
            if enriched["suggested_monthly_contribution"]
            else None
        ),
        "projected_completion": (
            enriched["projected_completion"].isoformat()
            if enriched["projected_completion"]
            else None
        ),
        "pace_note": enriched["pace_note"],
        "progress_pct": enriched["progress_pct"],
    }
    if data["required_monthly"]:
        summary = (
            f"{matched.name}: ₹{data['remaining']:,.0f} remaining over "
            f"{data['months_remaining']} month(s) - about "
            f"₹{data['required_monthly']:,.0f} per month."
        )
    else:
        summary = f"{matched.name}: {enriched['pace_note']}"
    return ToolResult("get_goal_requirement", {"goal": matched.name}, data, summary)


def get_anomalies(session: Session, user: User, **_: Any) -> ToolResult:
    from app.services import anomaly_service

    result = anomaly_service.run_detection(session, user, persist=False)
    if not result["sufficient_data"]:
        data = {"available": False, "reason": result["message"]}
        return ToolResult("get_anomalies", {}, data, result["message"])

    data = {
        "available": True,
        "method": result["method"],
        "baseline": result["baseline"],
        "anomalies": [
            {
                "merchant": a["transaction"].merchant,
                "amount": float(a["transaction"].amount),
                "date": a["transaction"].occurred_on.isoformat(),
                "category": (a["transaction"].category.name if a["transaction"].category else None),
                "reason": a["reason"],
                "score": a["score"],
            }
            for a in result["anomalies"][:5]
        ],
    }
    summary = (
        f"{len(data['anomalies'])} unusual transaction(s) detected: "
        + "; ".join(f"{a['merchant']} ₹{a['amount']:,.0f}" for a in data["anomalies"][:3])
        if data["anomalies"]
        else "No unusual transactions detected."
    )
    return ToolResult("get_anomalies", {}, data, summary)


def compare_periods(
    session: Session, user: User, period: DateRange, label: str = "", **_: Any
) -> ToolResult:
    """Why spending changed: this period vs the one before it, by category."""
    breakdown = analytics_service.category_breakdown(session, user, period, compare=True)
    previous = period.previous()

    current_total = sum(float(c["amount"]) for c in breakdown)
    previous_total = sum(float(c["previous_amount"] or 0) for c in breakdown)

    movers = [
        {
            "category": c["category"],
            "current": float(c["amount"]),
            "previous": float(c["previous_amount"] or 0),
            "change": float(c["amount"]) - float(c["previous_amount"] or 0),
            "change_pct": c["change_pct"],
        }
        for c in breakdown
        if c["previous_amount"] is not None
    ]
    movers.sort(key=lambda m: abs(m["change"]), reverse=True)

    data = {
        "available": bool(breakdown),
        "current_period": period.as_dict(),
        "previous_period": previous.as_dict(),
        "current_total": round(current_total, 2),
        "previous_total": round(previous_total, 2),
        "total_change": round(current_total - previous_total, 2),
        "total_change_pct": (
            round((current_total - previous_total) / previous_total * 100, 2)
            if previous_total
            else None
        ),
        "biggest_movers": movers[:6],
        "reason": None if breakdown else "No spending recorded to compare.",
    }
    if breakdown and movers:
        direction = "higher" if current_total >= previous_total else "lower"
        summary = (
            f"Spending in {label or 'this period'} was ₹{current_total:,.0f}, "
            f"₹{abs(current_total - previous_total):,.0f} {direction} than the "
            f"previous comparable period. Biggest movers: "
            + ", ".join(
                f"{m['category']} {'+' if m['change'] >= 0 else '-'}₹{abs(m['change']):,.0f}"
                for m in movers[:4]
            )
        )
    else:
        summary = data["reason"] or "No comparison available."
    return ToolResult("compare_periods", {"period": period.as_dict()}, data, summary)


# Registry exposed to the API for documentation.
TOOL_REGISTRY: dict[str, Callable[..., ToolResult]] = {
    "get_monthly_spending": get_monthly_spending,
    "get_category_spending": get_category_spending,
    "get_recent_transactions": get_recent_transactions,
    "get_budget_status": get_budget_status,
    "get_goal_progress": get_goal_progress,
    "get_goal_requirement": get_goal_requirement,
    "get_financial_health": get_financial_health,
    "get_forecast": get_forecast,
    "get_insights": get_insights,
    "get_top_merchants": get_top_merchants,
    "get_savings_simulation": get_savings_simulation,
    "get_anomalies": get_anomalies,
    "compare_periods": compare_periods,
}

TOOL_DESCRIPTIONS = [
    {
        "name": "get_monthly_spending",
        "description": "Income, expenses, net savings and savings rate for a period",
    },
    {
        "name": "get_category_spending",
        "description": "Spend for a specific category, or the top categories",
    },
    {
        "name": "get_recent_transactions",
        "description": "The most recent transactions with merchant and category",
    },
    {
        "name": "get_budget_status",
        "description": "Current month's budget limits, spend, utilisation and warnings",
    },
    {"name": "get_goal_progress", "description": "Progress across all financial goals"},
    {
        "name": "get_goal_requirement",
        "description": "Monthly contribution needed to hit a specific goal",
    },
    {
        "name": "get_financial_health",
        "description": "Financial health score with its component breakdown",
    },
    {
        "name": "get_forecast",
        "description": "Projected income, expenses and net cash flow for next month",
    },
    {
        "name": "get_insights",
        "description": "Current generated insights with their supporting figures",
    },
    {"name": "get_top_merchants", "description": "Highest-spend merchants for a period"},
    {
        "name": "get_savings_simulation",
        "description": "What reducing a category by a given percent would save",
    },
    {
        "name": "get_anomalies",
        "description": "Unusual transactions with the reason each was flagged",
    },
    {
        "name": "compare_periods",
        "description": "Why spending changed vs the previous comparable period",
    },
]
