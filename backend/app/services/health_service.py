"""Financial health score.

This is an application-generated educational metric, not a credit score and not
professional advice. Every component is a transparent, reproducible measurement
of the user's own recorded data, each is returned with its own sub-score and
explanation, and components that cannot be measured are excluded from the
weighting rather than being guessed at.

Components and weights (renormalised over whatever is measurable):

    savings_rate        30%   net savings / income over the last 3 months
    budget_adherence    20%   how close actual spend was to the set limits
    spending_stability  15%   month-to-month volatility of expenses
    emergency_fund      15%   months of expenses covered by the emergency goal
    goal_progress       10%   average progress across active goals
    income_consistency  10%   variability of recorded income
"""

from __future__ import annotations

import logging
import statistics
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import GoalStatus, TransactionType, User
from app.repositories import transaction_repository as repo
from app.services import budget_service, goal_service
from app.utils.dates import add_months, month_key, month_start
from app.utils.money import clamp, percent_of, to_decimal

logger = logging.getLogger(__name__)

WEIGHTS = {
    "savings_rate": 0.30,
    "budget_adherence": 0.20,
    "spending_stability": 0.15,
    "emergency_fund": 0.15,
    "goal_progress": 0.10,
    "income_consistency": 0.10,
}

ANALYSIS_MONTHS = 3
# A 20% savings rate scores 100. Chosen to match the widely used 50/30/20
# guideline; documented so the target is inspectable rather than arbitrary.
SAVINGS_RATE_TARGET = 20.0
# Six months of expenses is the conventional emergency-fund target.
EMERGENCY_FUND_TARGET_MONTHS = 6


def _grade(score: float) -> tuple[str, str]:
    if score >= 85:
        return "A", "Excellent"
    if score >= 70:
        return "B", "Good"
    if score >= 55:
        return "C", "Fair"
    if score >= 40:
        return "D", "Needs attention"
    return "E", "At risk"


def _impact(score: float) -> str:
    if score >= 70:
        return "positive"
    if score >= 45:
        return "neutral"
    return "negative"


def _monthly_totals(
    session: Session, user: User, today: date, months: int
) -> list[tuple[str, Decimal, Decimal]]:
    """``(month_key, income, expense)`` for the last ``months`` complete-ish months."""
    start = month_start(add_months(today, -(months - 1)))
    transactions = repo.list_in_range(session, user.id, start, today)

    income: dict[str, Decimal] = {}
    expense: dict[str, Decimal] = {}
    for t in transactions:
        key = month_key(t.occurred_on)
        if t.type == TransactionType.INCOME:
            income[key] = income.get(key, Decimal("0")) + Decimal(t.amount)
        elif t.type == TransactionType.EXPENSE:
            expense[key] = expense.get(key, Decimal("0")) + Decimal(t.amount)

    keys = sorted(set(income) | set(expense))
    return [(k, income.get(k, Decimal("0")), expense.get(k, Decimal("0"))) for k in keys]


def _savings_rate_component(totals: list[tuple[str, Decimal, Decimal]]) -> dict:
    total_income = sum((row[1] for row in totals), Decimal("0"))
    total_expense = sum((row[2] for row in totals), Decimal("0"))

    if total_income <= 0:
        return {
            "key": "savings_rate",
            "label": "Savings rate",
            "score": 0.0,
            "weight": WEIGHTS["savings_rate"],
            "value": "No income recorded",
            "impact": "negative",
            "explanation": (
                "No income has been recorded in the last "
                f"{ANALYSIS_MONTHS} months, so a savings rate cannot be computed. "
                "Add your income transactions to score this component."
            ),
            "available": False,
        }

    rate = percent_of(total_income - total_expense, total_income)
    # Linear up to the target, then a slower climb so extreme rates do not
    # dominate the overall score.
    if rate <= 0:
        score = 0.0
    elif rate >= SAVINGS_RATE_TARGET:
        score = clamp(85 + (rate - SAVINGS_RATE_TARGET) * 0.75)
    else:
        score = clamp(rate / SAVINGS_RATE_TARGET * 85)

    if rate <= 0:
        explanation = (
            f"You spent more than you earned over the last {len(totals)} month(s) "
            f"(₹{total_expense:,.0f} spent against ₹{total_income:,.0f} earned). "
            "Bringing spending below income is the single biggest lever on this score."
        )
    else:
        explanation = (
            f"You saved {rate:.1f}% of your income over the last {len(totals)} "
            f"month(s) - ₹{total_income - total_expense:,.0f} out of ₹{total_income:,.0f}. "
            f"A rate of {SAVINGS_RATE_TARGET:.0f}% scores full marks here."
        )

    return {
        "key": "savings_rate",
        "label": "Savings rate",
        "score": round(score, 1),
        "weight": WEIGHTS["savings_rate"],
        "value": f"{rate:.1f}%",
        "impact": _impact(score),
        "explanation": explanation,
        "available": True,
    }


def _budget_adherence_component(session: Session, user: User, today: date) -> dict:
    """Score how well actual spend respected the limits that were set."""
    scores: list[float] = []
    detail: list[str] = []

    for offset in range(ANALYSIS_MONTHS):
        month = month_start(add_months(today, -offset))
        budget = budget_service.get_budget_for_month(session, user, month)
        if budget is None or not budget.items:
            continue

        status = budget_service.compute_status(session, user, budget, today)
        # For the current (incomplete) month, judge pace rather than the raw
        # total: being at 60% on day 15 is fine, and penalising it would be wrong.
        is_current = month_start(today) == month
        for item in status["items"]:
            utilization = item["utilization"]
            if is_current:
                expected = max(status["expected_utilization"], 1.0)
                ratio = utilization / expected
                # 1.0 = exactly on pace. Penalise only overspending pace.
                item_score = 100.0 if ratio <= 1.0 else clamp(100 - (ratio - 1) * 100)
            else:
                item_score = 100.0 if utilization <= 100 else clamp(100 - (utilization - 100) * 2)
            scores.append(item_score)

        if is_current and status["warnings"]:
            detail.extend(status["warnings"][:2])

    if not scores:
        return {
            "key": "budget_adherence",
            "label": "Budget adherence",
            "score": 0.0,
            "weight": WEIGHTS["budget_adherence"],
            "value": "No budget set",
            "impact": "neutral",
            "explanation": (
                "No budget with category limits exists for the last "
                f"{ANALYSIS_MONTHS} months, so adherence cannot be measured. "
                "This component is excluded from your score until you set one."
            ),
            "available": False,
        }

    score = statistics.fmean(scores)
    explanation = (
        f"Measured across {len(scores)} category limit(s) over the last "
        f"{ANALYSIS_MONTHS} months. Staying within a limit scores full marks; "
        "exceeding it costs 2 points per percent over. For the current month, "
        "your pace is compared against how much of the month has elapsed."
    )
    if detail:
        explanation += " Currently: " + " ".join(detail)

    return {
        "key": "budget_adherence",
        "label": "Budget adherence",
        "score": round(score, 1),
        "weight": WEIGHTS["budget_adherence"],
        "value": f"{score:.0f}/100 across {len(scores)} limits",
        "impact": _impact(score),
        "explanation": explanation,
        "available": True,
    }


def _stability_component(totals: list[tuple[str, Decimal, Decimal]]) -> dict:
    expenses = [float(row[2]) for row in totals if row[2] > 0]
    if len(expenses) < 2:
        return {
            "key": "spending_stability",
            "label": "Spending consistency",
            "score": 0.0,
            "weight": WEIGHTS["spending_stability"],
            "value": "Not enough history",
            "impact": "neutral",
            "explanation": (
                "At least two months of expenses are needed to measure how "
                "consistent your spending is. This component is excluded for now."
            ),
            "available": False,
        }

    mean = statistics.fmean(expenses)
    stdev = statistics.stdev(expenses)
    cv = stdev / mean if mean > 0 else 0.0
    # CV of 0 scores 100; CV of 0.5 (spending swinging ±50%) scores 0.
    score = clamp(100 * (1 - cv / 0.5))

    return {
        "key": "spending_stability",
        "label": "Spending consistency",
        "score": round(score, 1),
        "weight": WEIGHTS["spending_stability"],
        "value": f"±{cv * 100:.0f}% month to month",
        "impact": _impact(score),
        "explanation": (
            f"Your monthly expenses averaged ₹{mean:,.0f} with a standard deviation "
            f"of ₹{stdev:,.0f} ({cv * 100:.0f}% of the average). Predictable "
            "spending makes budgeting and forecasting more reliable; swings above "
            "50% score zero here."
        ),
        "available": True,
    }


def _emergency_fund_component(
    session: Session, user: User, totals: list[tuple[str, Decimal, Decimal]]
) -> dict:
    expenses = [row[2] for row in totals if row[2] > 0]
    monthly_expense = (
        statistics.fmean([float(e) for e in expenses])
        if expenses
        else float(to_decimal(user.typical_monthly_expenses))
    )

    goals = goal_service.list_goals(session, user)
    emergency = next(
        (
            g
            for g in goals
            if "emergency" in g.name.lower() or g.goal_type.lower() == "emergency_fund"
        ),
        None,
    )
    saved = to_decimal(emergency.current_amount) if emergency else Decimal("0")

    if monthly_expense <= 0:
        return {
            "key": "emergency_fund",
            "label": "Emergency fund",
            "score": 0.0,
            "weight": WEIGHTS["emergency_fund"],
            "value": "Unknown",
            "impact": "neutral",
            "explanation": (
                "Monthly expenses are unknown, so emergency-fund coverage cannot "
                "be expressed in months. This component is excluded."
            ),
            "available": False,
        }

    months_covered = float(saved) / monthly_expense
    score = clamp(months_covered / EMERGENCY_FUND_TARGET_MONTHS * 100)

    if emergency is None:
        explanation = (
            "No emergency-fund goal was found. Finora looks for an active goal "
            "named 'Emergency Fund' (or of type emergency_fund) and measures it "
            f"against {EMERGENCY_FUND_TARGET_MONTHS} months of your average "
            f"expenses (₹{monthly_expense * EMERGENCY_FUND_TARGET_MONTHS:,.0f}). "
            "Create one to score this component."
        )
    else:
        explanation = (
            f"Your emergency fund holds ₹{saved:,.0f}, which covers "
            f"{months_covered:.1f} months of your average monthly expenses "
            f"(₹{monthly_expense:,.0f}). Full marks at "
            f"{EMERGENCY_FUND_TARGET_MONTHS} months of cover."
        )

    return {
        "key": "emergency_fund",
        "label": "Emergency fund",
        "score": round(score, 1),
        "weight": WEIGHTS["emergency_fund"],
        "value": f"{months_covered:.1f} months covered",
        "impact": _impact(score),
        "explanation": explanation,
        "available": True,
    }


def _goal_component(session: Session, user: User) -> dict:
    goals = [g for g in goal_service.list_goals(session, user) if g.status == GoalStatus.ACTIVE]
    if not goals:
        return {
            "key": "goal_progress",
            "label": "Goal progress",
            "score": 0.0,
            "weight": WEIGHTS["goal_progress"],
            "value": "No active goals",
            "impact": "neutral",
            "explanation": (
                "You have no active financial goals, so progress cannot be "
                "measured. This component is excluded from your score."
            ),
            "available": False,
        }

    progresses = [min(100.0, percent_of(g.current_amount, g.target_amount)) for g in goals]
    score = statistics.fmean(progresses)

    return {
        "key": "goal_progress",
        "label": "Goal progress",
        "score": round(score, 1),
        "weight": WEIGHTS["goal_progress"],
        "value": f"{score:.0f}% average across {len(goals)} goal(s)",
        "impact": _impact(score),
        "explanation": (
            f"Average completion across your {len(goals)} active goal(s): "
            + ", ".join(
                f"{g.name} {percent_of(g.current_amount, g.target_amount):.0f}%" for g in goals[:4]
            )
            + "."
        ),
        "available": True,
    }


def _income_consistency_component(totals: list[tuple[str, Decimal, Decimal]]) -> dict:
    incomes = [float(row[1]) for row in totals if row[1] > 0]
    if len(incomes) < 2:
        return {
            "key": "income_consistency",
            "label": "Income consistency",
            "score": 0.0,
            "weight": WEIGHTS["income_consistency"],
            "value": "Not enough history",
            "impact": "neutral",
            "explanation": (
                "At least two months with recorded income are needed to measure "
                "consistency. This component is excluded for now."
            ),
            "available": False,
        }

    mean = statistics.fmean(incomes)
    stdev = statistics.stdev(incomes)
    cv = stdev / mean if mean > 0 else 0.0
    score = clamp(100 * (1 - cv / 0.4))

    return {
        "key": "income_consistency",
        "label": "Income consistency",
        "score": round(score, 1),
        "weight": WEIGHTS["income_consistency"],
        "value": f"±{cv * 100:.0f}% month to month",
        "impact": _impact(score),
        "explanation": (
            f"Your monthly income averaged ₹{mean:,.0f} with a deviation of "
            f"₹{stdev:,.0f} ({cv * 100:.0f}%). Steady income makes planning "
            "easier; variable income is not a fault, but it does warrant a "
            "larger emergency buffer."
        ),
        "available": True,
    }


def compute_health_score(session: Session, user: User, today: date | None = None) -> dict:
    today = today or date.today()
    totals = _monthly_totals(session, user, today, ANALYSIS_MONTHS)

    if not totals:
        return {
            "score": 0.0,
            "grade": "-",
            "band": "Not enough data",
            "components": [],
            "positives": [],
            "negatives": [],
            "methodology": methodology_text(),
            "disclaimer": DISCLAIMER,
            "computed_at": datetime.now(UTC),
            "has_data": False,
        }

    components = [
        _savings_rate_component(totals),
        _budget_adherence_component(session, user, today),
        _stability_component(totals),
        _emergency_fund_component(session, user, totals),
        _goal_component(session, user),
        _income_consistency_component(totals),
    ]

    # Renormalise weights over measurable components only, so a user without a
    # budget is not silently penalised for a component we cannot assess.
    measurable = [c for c in components if c["available"]]
    total_weight = sum(c["weight"] for c in measurable)
    if total_weight > 0:
        score = sum(c["score"] * c["weight"] for c in measurable) / total_weight
    else:
        score = 0.0

    grade, band = _grade(score)
    positives = [c["explanation"] for c in measurable if c["impact"] == "positive"]
    negatives = [c["explanation"] for c in measurable if c["impact"] == "negative"]

    return {
        "score": round(score, 1),
        "grade": grade,
        "band": band,
        "components": components,
        "positives": positives,
        "negatives": negatives,
        "methodology": methodology_text(),
        "disclaimer": DISCLAIMER,
        "computed_at": datetime.now(UTC),
        "has_data": True,
    }


DISCLAIMER = (
    "This score is an educational metric generated by Finora from the data you "
    "have entered. It is not a credit score, not a professional assessment, and "
    "not financial advice. It is only as accurate as the transactions you record."
)


def methodology_text() -> str:
    parts = [
        "The score is a weighted average of six components, each measured from "
        "your own recorded data over the last 3 months:",
        "savings rate (30%) - net savings divided by income, with a 20% rate scoring full marks;",
        "budget adherence (20%) - actual spend against the limits you set, judged on pace for the current month;",
        "spending consistency (15%) - month-to-month volatility of expenses, measured as coefficient of variation;",
        "emergency fund (15%) - months of average expenses covered by your emergency-fund goal, targeting 6 months;",
        "goal progress (10%) - average completion across active goals;",
        "income consistency (10%) - variability of recorded monthly income.",
        "Components that cannot be measured (no budget set, no goals, too little "
        "history) are excluded and the remaining weights are renormalised, rather "
        "than being scored as zero.",
    ]
    return " ".join(parts)


def score_for_ai(session: Session, user: User, today: date | None = None) -> dict:
    result = compute_health_score(session, user, today)
    if not result["has_data"]:
        return {"available": False, "reason": "No transaction history to score yet."}
    return {
        "available": True,
        "score": result["score"],
        "grade": result["grade"],
        "band": result["band"],
        "components": [
            {
                "component": c["label"],
                "score": c["score"],
                "value": c["value"],
                "measured": c["available"],
            }
            for c in result["components"]
        ],
        "disclaimer": DISCLAIMER,
    }
