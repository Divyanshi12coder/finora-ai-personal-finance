"""Financial goals.

Progress is derived from the contribution ledger, and the projection is based on
the user's actual contribution pace rather than an assumption. Where there is no
pace to measure yet, the response says so instead of projecting a date.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import FinancialGoal, GoalContribution, GoalStatus, User
from app.schemas.goal import ContributionCreate, GoalCreate, GoalUpdate
from app.utils.dates import add_months, month_start
from app.utils.money import percent_of, quantize, to_decimal

logger = logging.getLogger(__name__)


class GoalError(Exception):
    """Business-rule violation; routers map this to a 400."""


def list_goals(session: Session, user: User) -> list[FinancialGoal]:
    stmt = (
        select(FinancialGoal)
        .where(FinancialGoal.user_id == user.id)
        .options(joinedload(FinancialGoal.contributions))
        .order_by(FinancialGoal.status, FinancialGoal.created_at.desc())
    )
    return list(session.scalars(stmt).unique().all())


def get_goal(session: Session, user: User, goal_id: str) -> FinancialGoal | None:
    stmt = (
        select(FinancialGoal)
        .where(FinancialGoal.id == goal_id, FinancialGoal.user_id == user.id)
        .options(joinedload(FinancialGoal.contributions))
    )
    return session.scalars(stmt).unique().first()


def create_goal(session: Session, user: User, payload: GoalCreate) -> FinancialGoal:
    goal = FinancialGoal(
        user_id=user.id,
        name=payload.name,
        goal_type=payload.goal_type,
        target_amount=payload.target_amount,
        current_amount=payload.current_amount,
        target_date=payload.target_date,
        icon=payload.icon,
        color=payload.color,
        notes=payload.notes,
        status=(
            GoalStatus.ACHIEVED
            if payload.current_amount >= payload.target_amount
            else GoalStatus.ACTIVE
        ),
    )
    session.add(goal)
    session.flush()

    # An opening balance is a contribution too - the ledger must reconcile.
    if payload.current_amount > 0:
        session.add(
            GoalContribution(
                goal_id=goal.id,
                amount=payload.current_amount,
                occurred_on=date.today(),
                note="Opening balance",
            )
        )
        session.flush()
    return goal


def update_goal(session: Session, goal: FinancialGoal, payload: GoalUpdate) -> FinancialGoal:
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(goal, field, value)

    # Raising the target on a completed goal reopens it; hitting the new target
    # closes it again.
    if goal.current_amount >= goal.target_amount and goal.status == GoalStatus.ACTIVE:
        goal.status = GoalStatus.ACHIEVED
    elif goal.current_amount < goal.target_amount and goal.status == GoalStatus.ACHIEVED:
        goal.status = GoalStatus.ACTIVE

    session.flush()
    return goal


def delete_goal(session: Session, goal: FinancialGoal) -> None:
    session.delete(goal)
    session.flush()


def add_contribution(
    session: Session, goal: FinancialGoal, payload: ContributionCreate
) -> FinancialGoal:
    """Add (or withdraw) money, keeping the running total and ledger in step."""
    amount = to_decimal(payload.amount)
    new_total = to_decimal(goal.current_amount) + amount

    if new_total < 0:
        raise GoalError(
            f"That withdrawal would take the goal below zero "
            f"(current balance ₹{goal.current_amount:,.2f})."
        )

    contribution = GoalContribution(
        goal_id=goal.id,
        amount=amount,
        occurred_on=payload.occurred_on or date.today(),
        note=payload.note,
    )
    session.add(contribution)

    goal.current_amount = new_total
    if new_total >= to_decimal(goal.target_amount):
        goal.status = GoalStatus.ACHIEVED
    elif goal.status == GoalStatus.ACHIEVED:
        goal.status = GoalStatus.ACTIVE

    session.flush()
    session.refresh(goal)
    logger.info("Goal %s contribution %s -> total %s", goal.id, amount, new_total)
    return goal


def _monthly_pace(goal: FinancialGoal, today: date) -> Decimal | None:
    """Average monthly contribution, excluding the opening balance."""
    contributions = [
        c for c in goal.contributions if c.note != "Opening balance" and to_decimal(c.amount) > 0
    ]
    if not contributions:
        return None

    first = min(c.occurred_on for c in contributions)
    months = max(1, (today.year - first.year) * 12 + (today.month - first.month) + 1)
    total = sum((to_decimal(c.amount) for c in contributions), Decimal("0"))
    return total / Decimal(months)


def enrich(goal: FinancialGoal, today: date | None = None) -> dict:
    """Attach the computed progress fields the UI needs."""
    today = today or date.today()
    target = to_decimal(goal.target_amount)
    current = to_decimal(goal.current_amount)
    remaining = max(Decimal("0"), target - current)
    progress = min(100.0, percent_of(current, target))

    months_remaining: int | None = None
    suggested: Decimal | None = None
    if goal.target_date:
        months_remaining = max(
            0,
            (goal.target_date.year - today.year) * 12 + (goal.target_date.month - today.month),
        )
        if remaining > 0:
            # Always at least one month, so the number is actionable rather than
            # a division by zero on the final month.
            suggested = quantize(remaining / Decimal(max(1, months_remaining)))

    pace = _monthly_pace(goal, today)
    projected_completion: date | None = None
    on_track: bool | None = None

    if remaining <= 0:
        projected_completion = today
        on_track = True
        pace_note = "Goal reached. Nicely done."
    elif pace and pace > 0:
        months_needed = int((remaining / pace).to_integral_value(rounding="ROUND_CEILING"))
        projected_completion = add_months(month_start(today), months_needed)
        if goal.target_date:
            on_track = projected_completion <= goal.target_date
            if on_track:
                pace_note = (
                    f"At your recent pace of ₹{pace:,.0f}/month you'll reach this "
                    f"around {projected_completion.strftime('%b %Y')} - ahead of your "
                    f"{goal.target_date.strftime('%b %Y')} target."
                )
            else:
                shortfall = suggested - pace if suggested else Decimal("0")
                pace_note = (
                    f"At ₹{pace:,.0f}/month you'd finish around "
                    f"{projected_completion.strftime('%b %Y')}, after your "
                    f"{goal.target_date.strftime('%b %Y')} target. Adding about "
                    f"₹{max(Decimal('0'), shortfall):,.0f} more per month would close the gap."
                )
        else:
            pace_note = (
                f"At your recent pace of ₹{pace:,.0f}/month you'll reach this around "
                f"{projected_completion.strftime('%b %Y')}."
            )
    elif suggested:
        pace_note = (
            f"No contributions recorded yet. Saving ₹{suggested:,.0f}/month would "
            f"reach ₹{target:,.0f} by {goal.target_date.strftime('%b %Y')}."
        )
    else:
        pace_note = (
            "Add a target date or record a contribution and Finora will project a "
            "completion date from your actual pace."
        )

    return {
        "id": goal.id,
        "name": goal.name,
        "goal_type": goal.goal_type,
        "target_amount": quantize(target),
        "current_amount": quantize(current),
        "target_date": goal.target_date,
        "status": goal.status,
        "icon": goal.icon,
        "color": goal.color,
        "notes": goal.notes,
        "created_at": goal.created_at,
        "progress_pct": progress,
        "remaining": quantize(remaining),
        "months_remaining": months_remaining,
        "suggested_monthly_contribution": suggested,
        "projected_completion": projected_completion,
        "on_track": on_track,
        "pace_note": pace_note,
        "contributions": sorted(
            goal.contributions, key=lambda c: (c.occurred_on, c.created_at), reverse=True
        )[:20],
    }


def summary(session: Session, user: User, today: date | None = None) -> dict:
    """Aggregate goal figures.

    Returned as plain primitives only: this payload is embedded in the dashboard
    response as an untyped dict, so ORM instances (which the serialiser cannot
    handle) must not leak into it.
    """
    goals = list_goals(session, user)
    active = [g for g in goals if g.status == GoalStatus.ACTIVE]
    achieved = [g for g in goals if g.status == GoalStatus.ACHIEVED]

    total_target = sum((to_decimal(g.target_amount) for g in active), Decimal("0"))
    total_saved = sum((to_decimal(g.current_amount) for g in active), Decimal("0"))

    next_goal: dict | None = None
    dated = [g for g in active if g.target_date]
    if dated:
        soonest = min(dated, key=lambda g: g.target_date or date.max)
        enriched = enrich(soonest, today)
        next_goal = {
            key: value
            for key, value in enriched.items()
            # `contributions` holds ORM rows; the dashboard card does not use them.
            if key != "contributions"
        }

    return {
        "total_goals": len(goals),
        "active_goals": len(active),
        "achieved_goals": len(achieved),
        "total_target": quantize(total_target),
        "total_saved": quantize(total_saved),
        "overall_progress": percent_of(total_saved, total_target),
        "next_goal": next_goal,
    }


def progress_for_ai(session: Session, user: User, today: date | None = None) -> dict:
    goals = list_goals(session, user)
    if not goals:
        return {"available": False, "reason": "No financial goals have been created yet."}

    return {
        "available": True,
        "goals": [
            {
                "name": g.name,
                "target": float(g.target_amount),
                "saved": float(g.current_amount),
                "remaining": float(
                    max(Decimal("0"), to_decimal(g.target_amount) - to_decimal(g.current_amount))
                ),
                "progress_pct": min(100.0, percent_of(g.current_amount, g.target_amount)),
                "target_date": g.target_date.isoformat() if g.target_date else None,
                "status": g.status.value,
                "suggested_monthly": (
                    float(enrich(g, today)["suggested_monthly_contribution"] or 0) or None
                ),
                "pace_note": enrich(g, today)["pace_note"],
            }
            for g in goals
        ],
    }
