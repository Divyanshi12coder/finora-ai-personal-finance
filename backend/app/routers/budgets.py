"""Budget endpoints, including AI budget recommendations."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import bad_request, get_current_user, not_found
from app.models import User
from app.schemas.budget import (
    ApplyRecommendationRequest,
    BudgetCreate,
    BudgetOut,
    BudgetRecommendationResponse,
    BudgetUpdate,
)
from app.schemas.common import Message
from app.services import budget_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/budgets", tags=["Budgets"])


@router.get(
    "",
    response_model=list[BudgetOut],
    summary="List budgets with live utilisation",
    description=(
        "Returns every budget with spent / remaining / utilisation / pace figures "
        "recomputed from the transactions table. No spend figure is stored, so "
        "these numbers cannot drift out of sync with the ledger."
    ),
)
def list_budgets(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> list[BudgetOut]:
    return [
        BudgetOut.model_validate(budget_service.compute_status(session, user, budget))
        for budget in budget_service.list_budgets(session, user)
    ]


@router.get(
    "/current",
    response_model=BudgetOut | None,
    summary="This month's budget",
)
def current_budget(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> BudgetOut | None:
    summary = budget_service.current_month_summary(session, user)
    return BudgetOut.model_validate(summary) if summary else None


@router.get(
    "/recommendations",
    response_model=BudgetRecommendationResponse,
    summary="AI budget recommendations",
    description=(
        "Analyses up to six complete months of per-category spending and proposes "
        "a realistic limit for each. Every suggestion is returned with the monthly "
        "series, mean, median, standard deviation, trend and a plain-English "
        "rationale, so the number can be judged rather than trusted blindly. "
        "Returns sufficient_data=false (with an explanation) rather than guessing "
        "when there is too little history."
    ),
)
def recommendations(
    period_month: str | None = Query(
        default=None, description="Target month as YYYY-MM; defaults to the current month"
    ),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> BudgetRecommendationResponse:
    return BudgetRecommendationResponse.model_validate(
        budget_service.recommend_budgets(session, user, period_month)
    )


@router.post(
    "/recommendations/apply",
    response_model=BudgetOut,
    summary="Apply recommended limits",
    description=(
        "Creates or updates the budget for the given month using the recommended "
        "amounts, storing the rationale alongside each limit."
    ),
)
def apply_recommendations(
    payload: ApplyRecommendationRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> BudgetOut:
    try:
        budget = budget_service.apply_recommendations(
            session, user, payload.period_month, payload.category_ids
        )
        session.commit()
    except budget_service.BudgetError as exc:
        session.rollback()
        raise bad_request(str(exc)) from exc

    session.refresh(budget)
    return BudgetOut.model_validate(budget_service.compute_status(session, user, budget))


@router.get("/{budget_id}", response_model=BudgetOut, summary="Get one budget")
def get_budget(
    budget_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> BudgetOut:
    budget = budget_service.get_budget(session, user, budget_id)
    if budget is None:
        raise not_found("Budget")
    return BudgetOut.model_validate(budget_service.compute_status(session, user, budget))


@router.post(
    "",
    response_model=BudgetOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a budget",
)
def create_budget(
    payload: BudgetCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> BudgetOut:
    try:
        budget = budget_service.create_budget(session, user, payload)
        session.commit()
    except budget_service.BudgetError as exc:
        session.rollback()
        raise bad_request(str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise bad_request("A budget already exists for that month") from exc

    session.refresh(budget)
    return BudgetOut.model_validate(budget_service.compute_status(session, user, budget))


@router.put("/{budget_id}", response_model=BudgetOut, summary="Update a budget")
def update_budget(
    budget_id: str,
    payload: BudgetUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> BudgetOut:
    budget = budget_service.get_budget(session, user, budget_id)
    if budget is None:
        raise not_found("Budget")

    try:
        updated = budget_service.update_budget(session, user, budget, payload)
        session.commit()
    except budget_service.BudgetError as exc:
        session.rollback()
        raise bad_request(str(exc)) from exc

    session.refresh(updated)
    return BudgetOut.model_validate(budget_service.compute_status(session, user, updated))


@router.delete("/{budget_id}", response_model=Message, summary="Delete a budget")
def delete_budget(
    budget_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Message:
    budget = budget_service.get_budget(session, user, budget_id)
    if budget is None:
        raise not_found("Budget")

    budget_service.delete_budget(session, budget)
    session.commit()
    return Message(detail="Budget deleted")
