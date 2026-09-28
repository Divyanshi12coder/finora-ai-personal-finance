"""Financial goal endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import bad_request, get_current_user, not_found
from app.models import User
from app.schemas.common import Message
from app.schemas.goal import ContributionCreate, GoalCreate, GoalOut, GoalUpdate
from app.services import goal_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/goals", tags=["Goals"])


@router.get(
    "",
    response_model=list[GoalOut],
    summary="List goals",
    description=(
        "Each goal is returned with computed progress, amount remaining, the "
        "monthly contribution needed to hit the target date, and a projected "
        "completion date derived from the user's actual contribution pace."
    ),
)
def list_goals(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> list[GoalOut]:
    return [
        GoalOut.model_validate(goal_service.enrich(goal))
        for goal in goal_service.list_goals(session, user)
    ]


@router.get("/summary", summary="Aggregate goal progress")
def summary(user: User = Depends(get_current_user), session: Session = Depends(get_db)) -> dict:
    return goal_service.summary(session, user)


@router.get("/{goal_id}", response_model=GoalOut, summary="Get one goal")
def get_goal(
    goal_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> GoalOut:
    goal = goal_service.get_goal(session, user, goal_id)
    if goal is None:
        raise not_found("Goal")
    return GoalOut.model_validate(goal_service.enrich(goal))


@router.post(
    "",
    response_model=GoalOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a goal",
)
def create_goal(
    payload: GoalCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> GoalOut:
    goal = goal_service.create_goal(session, user, payload)
    session.commit()
    session.refresh(goal)
    return GoalOut.model_validate(goal_service.enrich(goal))


@router.put("/{goal_id}", response_model=GoalOut, summary="Update a goal")
def update_goal(
    goal_id: str,
    payload: GoalUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> GoalOut:
    goal = goal_service.get_goal(session, user, goal_id)
    if goal is None:
        raise not_found("Goal")

    updated = goal_service.update_goal(session, goal, payload)
    session.commit()
    session.refresh(updated)
    return GoalOut.model_validate(goal_service.enrich(updated))


@router.post(
    "/{goal_id}/contributions",
    response_model=GoalOut,
    summary="Add money toward a goal",
    description=(
        "Records a contribution in the goal's ledger and updates its balance. "
        "A negative amount withdraws. The goal is marked achieved automatically "
        "once the target is reached."
    ),
)
def add_contribution(
    goal_id: str,
    payload: ContributionCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> GoalOut:
    goal = goal_service.get_goal(session, user, goal_id)
    if goal is None:
        raise not_found("Goal")

    try:
        updated = goal_service.add_contribution(session, goal, payload)
        session.commit()
    except goal_service.GoalError as exc:
        session.rollback()
        raise bad_request(str(exc)) from exc

    session.refresh(updated)
    return GoalOut.model_validate(goal_service.enrich(updated))


@router.delete("/{goal_id}", response_model=Message, summary="Delete a goal")
def delete_goal(
    goal_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Message:
    goal = goal_service.get_goal(session, user, goal_id)
    if goal is None:
        raise not_found("Goal")

    goal_service.delete_goal(session, goal)
    session.commit()
    return Message(detail="Goal deleted")
