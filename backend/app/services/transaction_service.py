"""Transaction business logic.

The write path for a transaction is:

    validated payload
        -> resolve/authorise category
        -> ML categorisation (when no category was supplied)
        -> persist
        -> log the prediction
        -> score for anomalies against the user's own history

Everything downstream (dashboard, budgets, analytics, forecasting, the AI
assistant) reads from the rows written here. Nothing is computed in the client.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models import Category, Transaction, TransactionSource, TransactionType, User
from app.repositories import transaction_repository as repo
from app.schemas.transaction import TransactionCreate, TransactionFilters, TransactionUpdate
from app.services import categorization_service, category_service

logger = logging.getLogger(__name__)


class TransactionError(Exception):
    """Raised for business-rule violations; routers map this to a 400."""


def list_transactions(
    session: Session, user: User, filters: TransactionFilters
) -> tuple[list[Transaction], int]:
    return repo.list_paginated(session, user.id, filters)


def get_transaction(session: Session, user: User, transaction_id: str) -> Transaction | None:
    return repo.get(session, user.id, transaction_id)


def _resolve_category(session: Session, user: User, category_id: str | None) -> Category | None:
    if not category_id:
        return None
    category = category_service.get_category_for_user(session, user, category_id)
    if category is None:
        raise TransactionError("Category not found or not accessible")
    return category


def create_transaction(
    session: Session,
    user: User,
    payload: TransactionCreate,
    source: TransactionSource = TransactionSource.MANUAL,
    run_anomaly_check: bool = True,
) -> Transaction:
    category = _resolve_category(session, user, payload.category_id)

    prediction_result = None
    ai_categorized = False
    ai_confidence: float | None = None

    # Only ask the model when the user did not choose a category themselves.
    if category is None and payload.auto_categorize:
        prediction_result, predicted_category = categorization_service.predict_for_transaction(
            session,
            user,
            description=payload.description,
            merchant=payload.merchant,
            payment_method=payload.payment_method,
            transaction_type=payload.type.value,
        )
        if prediction_result.should_auto_apply and predicted_category is not None:
            category = predicted_category
            ai_categorized = True
            ai_confidence = prediction_result.confidence
        elif prediction_result.available and prediction_result.category:
            # Confident enough to show, not confident enough to apply.
            logger.info(
                "Low-confidence prediction (%s @ %.2f) left unapplied",
                prediction_result.category,
                prediction_result.confidence or 0,
            )

    transaction = Transaction(
        user_id=user.id,
        category_id=category.id if category else None,
        amount=payload.amount,
        type=payload.type,
        merchant=payload.merchant,
        description=payload.description,
        occurred_on=payload.occurred_on,
        payment_method=payload.payment_method,
        notes=payload.notes,
        tags=payload.tags,
        source=source,
        receipt_id=payload.receipt_id,
        ai_categorized=ai_categorized,
        ai_confidence=ai_confidence,
    )
    session.add(transaction)
    session.flush()

    if prediction_result is not None:
        categorization_service.log_prediction(
            session,
            user,
            prediction_result,
            transaction=transaction,
            final_category_name=category.name if category else None,
            description=payload.description,
            merchant=payload.merchant,
            payment_method=payload.payment_method,
            transaction_type=payload.type.value,
        )

    if run_anomaly_check and payload.type == TransactionType.EXPENSE:
        # Imported here to avoid a circular import at module load.
        from app.services import anomaly_service

        anomaly_service.score_single_transaction(session, user, transaction)

    session.flush()
    return transaction


def update_transaction(
    session: Session, user: User, transaction: Transaction, payload: TransactionUpdate
) -> Transaction:
    data = payload.model_dump(exclude_unset=True)

    category_changed = False
    new_category: Category | None = None
    if "category_id" in data:
        new_category = _resolve_category(session, user, data.pop("category_id"))
        category_changed = (new_category.id if new_category else None) != transaction.category_id
        transaction.category_id = new_category.id if new_category else None
        if category_changed:
            # A human just overruled (or confirmed) the model. Either way this
            # is now a human-owned label, so drop the "AI categorised" badge.
            transaction.ai_categorized = False
            transaction.ai_confidence = None

    for field, value in data.items():
        setattr(transaction, field, value)

    session.flush()

    if category_changed:
        categorization_service.record_correction(session, user, transaction, new_category)

    # Amount or date changes invalidate the previous anomaly verdict.
    if ("amount" in data or "occurred_on" in data) and transaction.type == TransactionType.EXPENSE:
        from app.services import anomaly_service

        anomaly_service.score_single_transaction(session, user, transaction)

    session.flush()
    return transaction


def delete_transaction(session: Session, transaction: Transaction) -> None:
    session.delete(transaction)
    session.flush()


def bulk_delete(session: Session, user: User, ids: list[str]) -> int:
    return repo.delete_many(session, user.id, ids)


def has_any_transactions(session: Session, user: User) -> bool:
    return repo.count_all(session, user.id) > 0
