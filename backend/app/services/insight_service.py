"""The personalised insight engine.

Architecture:

    Transaction data
        -> aggregation (analytics_service, budget_service, anomaly_service)
        -> statistical detection (the rules in this module)
        -> structured InsightFact objects (numbers, periods, percentages)
        -> persisted Insight rows
        -> optional AI phrasing (ai_service) which may ONLY rewrite the text

Every detector is deterministic and every number in an insight comes from the
database. The AI layer never calculates: if the AI provider is unavailable the
insights are identical, just phrased by the built-in templates.

Detectors implemented:

* category spending increase / decrease vs the previous month
* budget at risk / exceeded
* unusual transactions (from the anomaly service)
* newly detected recurring charges
* savings-rate change
* savings opportunity (largest above-average category)
* goal falling behind its required pace
* projected cash-flow shortfall
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Insight,
    InsightSeverity,
    InsightType,
    User,
)
from app.repositories import transaction_repository as repo
from app.services import (
    analytics_service,
    anomaly_service,
    budget_service,
    forecasting_service,
    goal_service,
)
from app.utils.dates import DateRange, add_months, month_end, month_key, month_label, month_start
from app.utils.money import percentage_change

logger = logging.getLogger(__name__)

# Only report a category change when it is both proportionally and absolutely
# meaningful. A 40% jump on ₹120 of spending is noise, not an insight.
MIN_CHANGE_PCT = 18.0
MIN_CHANGE_AMOUNT = Decimal("500")
MAX_INSIGHTS_PER_RUN = 12


@dataclass
class InsightFact:
    """A structured, verifiable finding. The AI may rephrase, never recompute."""

    type: InsightType
    severity: InsightSeverity
    title: str
    summary: str
    why_it_matters: str
    suggested_action: str | None
    data: dict
    fingerprint: str
    period_start: date | None = None
    period_end: date | None = None
    priority: int = 50  # lower sorts first

    def to_model(self, user_id: str) -> Insight:
        return Insight(
            user_id=user_id,
            type=self.type,
            severity=self.severity,
            title=self.title,
            summary=self.summary,
            why_it_matters=self.why_it_matters,
            suggested_action=self.suggested_action,
            data=self.data,
            fingerprint=self.fingerprint,
            period_start=self.period_start,
            period_end=self.period_end,
        )


# --------------------------------------------------------------------------
# Detectors
# --------------------------------------------------------------------------
def _detect_category_changes(session: Session, user: User, today: date) -> list[InsightFact]:
    """Compare this month's category spend against last month's."""
    this_month = month_start(today)
    last_month = add_months(this_month, -1)

    current = DateRange(start=this_month, end=today)
    # Compare like with like: the same number of elapsed days in each month.
    # Comparing a partial month against a full one would report a "decrease"
    # for every category on the 2nd of the month.
    elapsed = today - this_month
    previous = DateRange(
        start=last_month,
        end=min(month_end(last_month), last_month + elapsed),
    )

    current_rows = {
        row[1]: (row[0], row[3], row[4])
        for row in repo.sum_by_category(session, user.id, current.start, current.end)
    }
    previous_rows = {
        row[1]: (row[0], row[3], row[4])
        for row in repo.sum_by_category(session, user.id, previous.start, previous.end)
    }

    facts: list[InsightFact] = []
    for name, (category_id, amount, count) in current_rows.items():
        previous_amount = previous_rows.get(name, (None, Decimal("0"), 0))[1]
        if previous_amount <= 0:
            continue

        change = amount - previous_amount
        change_pct = percentage_change(amount, previous_amount)
        if (
            change_pct is None
            or abs(change) < MIN_CHANGE_AMOUNT
            or abs(change_pct) < MIN_CHANGE_PCT
        ):
            continue

        data = {
            "category": name,
            "category_id": category_id,
            "current_amount": float(amount),
            "previous_amount": float(previous_amount),
            "change_amount": float(change),
            "change_percentage": change_pct,
            "transaction_count": count,
            "comparison": "same number of elapsed days in each month",
            "current_period": current.as_dict(),
            "previous_period": previous.as_dict(),
        }

        if change > 0:
            facts.append(
                InsightFact(
                    type=InsightType.SPENDING_INCREASE,
                    severity=(
                        InsightSeverity.WARNING if change_pct >= 40 else InsightSeverity.INFO
                    ),
                    title=f"{name} spending is up {change_pct:.0f}%",
                    summary=(
                        f"You've spent ₹{amount:,.0f} on {name} so far this month, "
                        f"against ₹{previous_amount:,.0f} over the same stretch of "
                        f"{month_label(last_month)} - an increase of ₹{change:,.0f}."
                    ),
                    why_it_matters=(
                        f"{name} is one of your larger variable categories, so a "
                        f"{change_pct:.0f}% shift here moves your monthly savings "
                        "more than most other changes would."
                    ),
                    suggested_action=(
                        f"Returning to your {month_label(last_month)} pace would free up "
                        f"about ₹{change:,.0f} this month."
                    ),
                    data=data,
                    fingerprint=f"spending_increase:{name}:{month_key(this_month)}",
                    period_start=current.start,
                    period_end=current.end,
                    priority=20 if change_pct >= 40 else 35,
                )
            )
        else:
            facts.append(
                InsightFact(
                    type=InsightType.SPENDING_DECREASE,
                    severity=InsightSeverity.POSITIVE,
                    title=f"{name} spending is down {abs(change_pct):.0f}%",
                    summary=(
                        f"You've spent ₹{amount:,.0f} on {name} this month against "
                        f"₹{previous_amount:,.0f} over the same stretch of "
                        f"{month_label(last_month)} - ₹{abs(change):,.0f} less."
                    ),
                    why_it_matters=(
                        f"Sustained over a year that pace difference is about "
                        f"₹{abs(change) * 12:,.0f}."
                    ),
                    suggested_action=(
                        f"Consider moving ₹{abs(change):,.0f} into a savings goal so "
                        "the reduction turns into progress rather than being absorbed elsewhere."
                    ),
                    data=data,
                    fingerprint=f"spending_decrease:{name}:{month_key(this_month)}",
                    period_start=current.start,
                    period_end=current.end,
                    priority=60,
                )
            )
    return facts


def _detect_budget_risks(session: Session, user: User, today: date) -> list[InsightFact]:
    summary = budget_service.current_month_summary(session, user, today)
    if summary is None:
        return []

    facts: list[InsightFact] = []
    for item in summary["items"]:
        if item["status"] not in {"at_risk", "exceeded", "watch"}:
            continue

        category = item["category"].name
        data = {
            "category": category,
            "limit": float(item["limit_amount"]),
            "spent": float(item["spent"]),
            "remaining": float(item["remaining"]),
            "utilization_pct": item["utilization"],
            "days_remaining": summary["days_remaining"],
            "expected_utilization_pct": summary["expected_utilization"],
            "projected_spend": float(item["projected_spend"]),
            "projected_overspend": float(item["projected_overspend"]),
        }

        if item["status"] == "exceeded":
            facts.append(
                InsightFact(
                    type=InsightType.BUDGET_EXCEEDED,
                    severity=InsightSeverity.CRITICAL,
                    title=f"{category} budget exceeded",
                    summary=(
                        f"You've spent ₹{item['spent']:,.0f} against a ₹{item['limit_amount']:,.0f} "
                        f"{category} limit - ₹{abs(item['remaining']):,.0f} over, with "
                        f"{summary['days_remaining']} days still to go."
                    ),
                    why_it_matters=(
                        "Overspending in one category has to come out of another or "
                        "out of savings; catching it before month-end is what makes "
                        "it recoverable."
                    ),
                    suggested_action=(
                        f"Pausing {category} spending for the rest of the month keeps "
                        f"the overspend at ₹{abs(item['remaining']):,.0f} rather than "
                        f"the ₹{item['projected_overspend']:,.0f} your current pace implies."
                    ),
                    data=data,
                    fingerprint=f"budget_exceeded:{category}:{month_key(today)}",
                    period_start=summary["period_month"],
                    period_end=month_end(summary["period_month"]),
                    priority=10,
                )
            )
        else:
            daily_allowance = (
                float(item["remaining"]) / summary["days_remaining"]
                if summary["days_remaining"] > 0
                else 0
            )
            facts.append(
                InsightFact(
                    type=InsightType.BUDGET_RISK,
                    severity=InsightSeverity.WARNING,
                    title=f"{category} budget is {item['utilization']:.0f}% used",
                    summary=(
                        f"You're {item['utilization']:.0f}% through your {category} budget "
                        f"with {summary['days_remaining']} days remaining, while only "
                        f"{summary['expected_utilization']:.0f}% of the month has elapsed."
                    ),
                    why_it_matters=(
                        f"At your current daily pace this category is projected to finish at "
                        f"₹{item['projected_spend']:,.0f} against a ₹{item['limit_amount']:,.0f} limit."
                    ),
                    suggested_action=(
                        f"Staying under ₹{daily_allowance:,.0f} a day on {category} keeps "
                        "you within the limit."
                    ),
                    data=data,
                    fingerprint=f"budget_risk:{category}:{month_key(today)}",
                    period_start=summary["period_month"],
                    period_end=month_end(summary["period_month"]),
                    priority=15,
                )
            )
    return facts


def _detect_anomalies(session: Session, user: User, today: date) -> list[InsightFact]:
    result = anomaly_service.run_detection(session, user, today, persist=True)
    if not result["sufficient_data"]:
        return []

    facts: list[InsightFact] = []
    for entry in result["anomalies"][:3]:
        transaction = entry["transaction"]
        detail = entry["detail"]
        facts.append(
            InsightFact(
                type=InsightType.ANOMALY,
                severity=InsightSeverity.WARNING,
                title=f"Unusual transaction: {transaction.merchant or 'unknown merchant'}",
                summary=entry["reason"],
                why_it_matters=(
                    "Transactions well outside your normal range are worth a second "
                    "look - they are how duplicate charges, incorrect amounts and "
                    "forgotten subscriptions get caught."
                ),
                suggested_action=(
                    "Confirm it if it was intentional, or mark it as expected so "
                    "Finora stops flagging similar amounts."
                ),
                data={
                    "transaction_id": transaction.id,
                    "amount": float(transaction.amount),
                    "merchant": transaction.merchant,
                    "occurred_on": transaction.occurred_on.isoformat(),
                    "category": transaction.category.name if transaction.category else None,
                    **detail,
                },
                fingerprint=f"anomaly:{transaction.id}",
                period_start=transaction.occurred_on,
                period_end=transaction.occurred_on,
                priority=12,
            )
        )
    return facts


def _detect_recurring(session: Session, user: User, today: date) -> list[InsightFact]:
    recurring = analytics_service.detect_recurring(session, user, today)
    if not recurring:
        return []

    monthly_total = sum(
        (r["average_amount"] for r in recurring if r["cadence"] == "monthly"), Decimal("0")
    )
    if monthly_total <= 0:
        return []

    top = [r for r in recurring if r["cadence"] == "monthly"][:5]
    return [
        InsightFact(
            type=InsightType.RECURRING_EXPENSE,
            severity=InsightSeverity.INFO,
            title=f"₹{monthly_total:,.0f}/month in recurring charges",
            summary=(
                f"Finora identified {len(top)} merchant(s) charging you on a monthly "
                f"cadence, totalling about ₹{monthly_total:,.0f} a month: "
                + ", ".join(f"{r['merchant']} (₹{r['average_amount']:,.0f})" for r in top)
                + "."
            ),
            why_it_matters=(
                f"That is roughly ₹{monthly_total * 12:,.0f} a year committed before "
                "you make a single discretionary decision."
            ),
            suggested_action=(
                "Review the list for subscriptions you no longer use - cancelling "
                "one is a permanent saving rather than a one-month effort."
            ),
            data={
                "monthly_total": float(monthly_total),
                "annual_total": float(monthly_total * 12),
                "merchants": [
                    {
                        "merchant": r["merchant"],
                        "average_amount": float(r["average_amount"]),
                        "occurrences": r["occurrences"],
                        "cadence": r["cadence"],
                        "next_expected": r["next_expected"].isoformat(),
                        "confidence": r["confidence"],
                    }
                    for r in top
                ],
                "detection_method": (
                    "median interval between charges per merchant, requiring at least "
                    "3 occurrences and consistent gaps"
                ),
            },
            fingerprint=f"recurring:{month_key(today)}",
            period_start=month_start(today),
            period_end=today,
            priority=45,
        )
    ]


def _detect_savings_rate(session: Session, user: User, today: date) -> list[InsightFact]:
    series = analytics_service.monthly_series(session, user, months=3, today=today)
    complete = [m for m in series if m["month"] != month_key(today)]
    if len(complete) < 2:
        return []

    latest, prior = complete[-1], complete[-2]
    if latest["income"] <= 0 or prior["income"] <= 0:
        return []

    change = latest["savings_rate"] - prior["savings_rate"]
    if abs(change) < 5:
        return []

    improving = change > 0
    return [
        InsightFact(
            type=InsightType.SAVINGS_RATE,
            severity=InsightSeverity.POSITIVE if improving else InsightSeverity.WARNING,
            title=(
                f"Savings rate {'rose' if improving else 'fell'} "
                f"{abs(change):.0f} points in {latest['label']}"
            ),
            summary=(
                f"You saved {latest['savings_rate']:.0f}% of your income in "
                f"{latest['label']} (₹{latest['savings']:,.0f} of ₹{latest['income']:,.0f}), "
                f"against {prior['savings_rate']:.0f}% in {prior['label']}."
            ),
            why_it_matters=(
                "Savings rate is the single number that determines how quickly your "
                "goals arrive - it matters more than the absolute amounts."
            ),
            suggested_action=(
                "Lock in the improvement by moving the difference into a goal."
                if improving
                else "Compare your category breakdown across the two months to find "
                "where the difference went."
            ),
            data={
                "current_month": latest["label"],
                "current_savings_rate": latest["savings_rate"],
                "previous_month": prior["label"],
                "previous_savings_rate": prior["savings_rate"],
                "change_points": round(change, 2),
                "current_savings": float(latest["savings"]),
                "current_income": float(latest["income"]),
            },
            fingerprint=f"savings_rate:{latest['month']}",
            period_start=None,
            period_end=None,
            priority=30 if not improving else 55,
        )
    ]


def _detect_savings_opportunity(session: Session, user: User, today: date) -> list[InsightFact]:
    """Find the category most above its own 3-month average."""
    this_month = month_start(today)
    current = DateRange(start=this_month, end=today)
    history_start = month_start(add_months(this_month, -3))
    history_end = month_end(add_months(this_month, -1))

    current_rows = {
        row[1]: row[3] for row in repo.sum_by_category(session, user.id, current.start, current.end)
    }
    if not current_rows:
        return []

    history_rows = repo.sum_by_category(session, user.id, history_start, history_end)
    months_of_history = 3
    averages = {row[1]: row[3] / months_of_history for row in history_rows}

    best_name: str | None = None
    best_excess = Decimal("0")
    best_average = Decimal("0")
    for name, amount in current_rows.items():
        average = averages.get(name)
        if not average or average <= 0:
            continue
        # Scale the month-to-date figure to a full month for a fair comparison.
        days_elapsed = max(1, (today - this_month).days + 1)
        days_in_month = (month_end(this_month) - this_month).days + 1
        projected = amount / Decimal(days_elapsed) * Decimal(days_in_month)
        excess = projected - average
        if excess > best_excess:
            best_excess, best_name, best_average = excess, name, average

    if best_name is None or best_excess < MIN_CHANGE_AMOUNT:
        return []

    return [
        InsightFact(
            type=InsightType.SAVINGS_OPPORTUNITY,
            severity=InsightSeverity.INFO,
            title=f"About ₹{best_excess:,.0f} recoverable in {best_name}",
            summary=(
                f"At your current pace {best_name} is on track for "
                f"₹{best_average + best_excess:,.0f} this month, against a 3-month "
                f"average of ₹{best_average:,.0f}."
            ),
            why_it_matters=(
                "This is the largest gap between your current pace and your own "
                "recent norm, which makes it the easiest place to recover money "
                "without changing your standard of living."
            ),
            suggested_action=(
                f"Returning {best_name} to its ₹{best_average:,.0f} average would "
                f"free up roughly ₹{best_excess:,.0f} this month, or "
                f"₹{best_excess * 12:,.0f} a year if sustained."
            ),
            data={
                "category": best_name,
                "three_month_average": float(best_average),
                "projected_this_month": float(best_average + best_excess),
                "potential_saving": float(best_excess),
                "annualised_saving": float(best_excess * 12),
                "method": "month-to-date spend extrapolated to full month vs 3-month average",
            },
            fingerprint=f"savings_opportunity:{best_name}:{month_key(today)}",
            period_start=current.start,
            period_end=current.end,
            priority=25,
        )
    ]


def _detect_goal_pace(session: Session, user: User, today: date) -> list[InsightFact]:
    facts: list[InsightFact] = []
    for goal in goal_service.list_goals(session, user):
        enriched = goal_service.enrich(goal, today)
        if enriched["on_track"] is not False or not goal.target_date:
            continue

        facts.append(
            InsightFact(
                type=InsightType.GOAL_PROGRESS,
                severity=InsightSeverity.WARNING,
                title=f"{goal.name} is behind schedule",
                summary=enriched["pace_note"],
                why_it_matters=(
                    f"You're {enriched['progress_pct']:.0f}% of the way to "
                    f"₹{goal.target_amount:,.0f} with "
                    f"{enriched['months_remaining']} month(s) until your target date."
                ),
                suggested_action=(
                    f"Contributing ₹{enriched['suggested_monthly_contribution']:,.0f} a "
                    f"month from here would still hit {goal.target_date.strftime('%b %Y')}."
                    if enriched["suggested_monthly_contribution"]
                    else "Consider moving the target date or lowering the target amount."
                ),
                data={
                    "goal": goal.name,
                    "target_amount": float(goal.target_amount),
                    "current_amount": float(goal.current_amount),
                    "remaining": float(enriched["remaining"]),
                    "progress_pct": enriched["progress_pct"],
                    "target_date": goal.target_date.isoformat(),
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
                },
                fingerprint=f"goal_progress:{goal.id}:{month_key(today)}",
                period_start=None,
                period_end=None,
                priority=28,
            )
        )
    return facts


def _detect_cashflow_risk(session: Session, user: User, today: date) -> list[InsightFact]:
    forecast = forecasting_service.build_forecast(session, user, horizon=3, today=today)
    if not forecast["sufficient_data"]:
        return []

    negative = [p for p in forecast["net_cashflow"] if p["is_forecast"] and p["value"] < 0]
    if not negative:
        return []

    first = negative[0]
    return [
        InsightFact(
            type=InsightType.CASHFLOW_RISK,
            severity=InsightSeverity.WARNING,
            title=f"Projected shortfall in {first['period']}",
            summary=(
                f"Based on {forecast['months_of_history']} months of history, "
                f"{first['period']} is projected to end ₹{abs(first['value']):,.0f} "
                "in deficit - expenses above income."
            ),
            why_it_matters=(
                "A projected deficit is easier to close before the month starts "
                "than to fund after it ends."
            ),
            suggested_action=(
                f"Trimming about ₹{abs(first['value']):,.0f} from planned spending, or "
                "bringing forward income, would close the projected gap."
            ),
            data={
                "period": first["period"],
                "projected_net": float(first["value"]),
                "interval_low": float(first["lower"]) if first["lower"] is not None else None,
                "interval_high": float(first["upper"]) if first["upper"] is not None else None,
                "method": forecast["expense"]["method"] if forecast["expense"] else None,
                "months_of_history": forecast["months_of_history"],
                "caveat": "80% prediction interval; a projection, not a guarantee.",
            },
            fingerprint=f"cashflow_risk:{first['period']}",
            period_start=None,
            period_end=None,
            priority=18,
        )
    ]


DETECTORS = [
    _detect_budget_risks,
    _detect_anomalies,
    _detect_category_changes,
    _detect_savings_opportunity,
    _detect_goal_pace,
    _detect_cashflow_risk,
    _detect_savings_rate,
    _detect_recurring,
]


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------
def generate_insights(
    session: Session, user: User, today: date | None = None, use_ai: bool = True
) -> tuple[list[Insight], bool]:
    """Run every detector, persist new findings, optionally add AI phrasing.

    Returns ``(insights, ai_used)``. Insights are deduplicated by fingerprint so
    running this repeatedly in a day does not pile up copies.
    """
    today = today or date.today()

    if not repo.count_all(session, user.id):
        return [], False

    facts: list[InsightFact] = []
    for detector in DETECTORS:
        try:
            facts.extend(detector(session, user, today))
        except Exception:
            # One failing detector must not take down the whole insights page.
            logger.exception("Insight detector %s failed", detector.__name__)

    facts.sort(key=lambda f: f.priority)
    facts = facts[:MAX_INSIGHTS_PER_RUN]

    existing = {
        row.fingerprint: row
        for row in session.scalars(select(Insight).where(Insight.user_id == user.id)).all()
    }

    created: list[Insight] = []
    for fact in facts:
        current = existing.get(fact.fingerprint)
        if current is not None:
            # Refresh the numbers in place; the finding is the same finding.
            current.title = fact.title
            current.summary = fact.summary
            current.why_it_matters = fact.why_it_matters
            current.suggested_action = fact.suggested_action
            current.data = fact.data
            current.severity = fact.severity
            created.append(current)
            continue

        row = fact.to_model(user.id)
        session.add(row)
        created.append(row)

    session.flush()

    ai_used = False
    if use_ai and created:
        from app.services import ai_service

        ai_used = ai_service.explain_insights(created)

    session.flush()
    logger.info("Generated %d insights for user %s (ai=%s)", len(created), user.id, ai_used)
    return created, ai_used


def list_insights(
    session: Session, user: User, include_dismissed: bool = False, limit: int = 30
) -> list[Insight]:
    stmt = select(Insight).where(Insight.user_id == user.id)
    if not include_dismissed:
        stmt = stmt.where(Insight.is_dismissed.is_(False))
    stmt = stmt.order_by(Insight.created_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def get_insight(session: Session, user: User, insight_id: str) -> Insight | None:
    stmt = select(Insight).where(Insight.id == insight_id, Insight.user_id == user.id)
    return session.scalars(stmt).first()


def mark_read(session: Session, insight: Insight) -> Insight:
    insight.is_read = True
    session.flush()
    return insight


def dismiss(session: Session, insight: Insight) -> Insight:
    insight.is_dismissed = True
    session.flush()
    return insight


def top_insights(session: Session, user: User, limit: int = 3) -> list[Insight]:
    """Highest-severity current insights, for the dashboard."""
    severity_rank = {
        InsightSeverity.CRITICAL: 0,
        InsightSeverity.WARNING: 1,
        InsightSeverity.INFO: 2,
        InsightSeverity.POSITIVE: 3,
    }
    insights = list_insights(session, user, limit=20)
    insights.sort(key=lambda i: (severity_rank.get(i.severity, 9), -i.created_at.timestamp()))
    return insights[:limit]


def insights_for_ai(session: Session, user: User, limit: int = 5) -> dict:
    insights = top_insights(session, user, limit=limit)
    if not insights:
        return {
            "available": False,
            "reason": "No insights have been generated yet. Add transactions and refresh insights.",
        }
    return {
        "available": True,
        "insights": [
            {
                "type": i.type.value,
                "severity": i.severity.value,
                "title": i.title,
                "summary": i.summary,
                "data": i.data,
            }
            for i in insights
        ],
    }
