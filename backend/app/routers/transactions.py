"""Transaction and category endpoints."""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import bad_request, get_current_user, not_found
from app.ml import categorizer
from app.models import TransactionType, User
from app.schemas.common import Message, Page
from app.schemas.transaction import (
    AnomalyFeedbackRequest,
    BulkDeleteRequest,
    CategorizePreviewRequest,
    CategorizePreviewResponse,
    CategoryCreate,
    CategoryOut,
    CategorySuggestion,
    CategoryUpdate,
    TransactionCreate,
    TransactionFilters,
    TransactionOut,
    TransactionUpdate,
)
from app.services import (
    anomaly_service,
    categorization_service,
    category_service,
    transaction_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Transactions"])


# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------
@router.get(
    "/categories",
    response_model=list[CategoryOut],
    summary="List categories",
    description="Returns the shared system categories plus any the user created.",
)
def list_categories(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> list[CategoryOut]:
    return [CategoryOut.model_validate(c) for c in category_service.list_categories(session, user)]


@router.post(
    "/categories",
    response_model=CategoryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom category",
)
def create_category(
    payload: CategoryCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> CategoryOut:
    try:
        category = category_service.create_category(session, user, payload)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise bad_request(f"You already have a category named '{payload.name}'") from exc
    session.refresh(category)
    return CategoryOut.model_validate(category)


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryOut,
    summary="Update a custom category",
)
def update_category(
    category_id: str,
    payload: CategoryUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> CategoryOut:
    category = category_service.get_category_for_user(session, user, category_id)
    if category is None:
        raise not_found("Category")
    if category.is_system:
        raise bad_request("System categories cannot be edited. Create your own category instead.")

    try:
        updated = category_service.update_category(session, category, payload)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise bad_request("You already have a category with that name") from exc
    session.refresh(updated)
    return CategoryOut.model_validate(updated)


@router.delete(
    "/categories/{category_id}",
    response_model=Message,
    summary="Delete a custom category",
    description=(
        "Deletes a user-created category. Transactions that referenced it become "
        "uncategorised rather than being deleted."
    ),
)
def delete_category(
    category_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Message:
    category = category_service.get_category_for_user(session, user, category_id)
    if category is None:
        raise not_found("Category")
    if category.is_system:
        raise bad_request("System categories cannot be deleted.")

    category_service.delete_category(session, category)
    session.commit()
    return Message(detail="Category deleted")


# --------------------------------------------------------------------------
# Transactions
# --------------------------------------------------------------------------
@router.get(
    "/transactions",
    response_model=Page[TransactionOut],
    summary="List transactions",
    description=(
        "Paginated, filterable, sortable transaction list. Only the authenticated "
        "user's transactions are ever returned."
    ),
)
def list_transactions(
    search: str | None = Query(default=None, max_length=120),
    type: TransactionType | None = None,
    category_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
    min_amount: Decimal | None = Query(default=None, ge=0),
    max_amount: Decimal | None = Query(default=None, ge=0),
    payment_method: str | None = Query(default=None, max_length=40),
    anomalies_only: bool = False,
    sort_by: str = Query(default="occurred_on"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Page[TransactionOut]:
    try:
        filters = TransactionFilters(
            search=search,
            type=type,
            category_id=category_id,
            start=start,
            end=end,
            min_amount=min_amount,
            max_amount=max_amount,
            payment_method=payment_method,
            anomalies_only=anomalies_only,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        raise bad_request(str(exc)) from exc

    items, total = transaction_service.list_transactions(session, user, filters)
    return Page.build(
        items=[TransactionOut.model_validate(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/transactions/payment-methods",
    response_model=list[str],
    summary="Payment methods already used",
    description="Powers the filter dropdown without hardcoding a list in the client.",
)
def payment_methods(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> list[str]:
    from app.repositories import transaction_repository as repo

    return repo.distinct_payment_methods(session, user.id)


@router.post(
    "/transactions/categorize-preview",
    response_model=CategorizePreviewResponse,
    summary="Preview the ML category for a transaction",
    description=(
        "Runs the trained TF-IDF + Logistic Regression classifier over the supplied "
        "text and returns the predicted category, its confidence, the runners-up, "
        "and the tokens that drove the prediction. Nothing is written to the "
        "database. Used by the transaction form to show the suggestion live."
    ),
)
def categorize_preview(
    payload: CategorizePreviewRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> CategorizePreviewResponse:
    result = categorizer.categorize(
        description=payload.description,
        merchant=payload.merchant,
        payment_method=payload.payment_method,
        transaction_type=payload.type.value,
        explain=True,
    )
    if not result.available or not result.category:
        return CategorizePreviewResponse(available=result.available, message=result.message)

    category = category_service.get_by_name(session, user, result.category)
    return CategorizePreviewResponse(
        available=True,
        category=result.category,
        category_id=category.id if category else None,
        confidence=result.confidence,
        alternatives=[
            CategorySuggestion(category=name, confidence=round(score, 4))
            for name, score in result.alternatives
        ],
        explanation=[
            {"token": token, "contribution": round(value, 4)} for token, value in result.explanation
        ],
        model_version=result.model_version,
        message=(
            None
            if result.should_auto_apply
            else "Confidence is below the auto-apply threshold, so this suggestion "
            "won't be applied automatically - pick a category to confirm."
        ),
    )


@router.get(
    "/transactions/{transaction_id}",
    response_model=TransactionOut,
    summary="Get one transaction",
)
def get_transaction(
    transaction_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> TransactionOut:
    transaction = transaction_service.get_transaction(session, user, transaction_id)
    if transaction is None:
        raise not_found("Transaction")
    return TransactionOut.model_validate(transaction)


@router.post(
    "/transactions",
    response_model=TransactionOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a transaction",
    description=(
        "Validates the payload, runs ML categorisation when no category was "
        "supplied, persists the row, logs the prediction for the feedback loop, "
        "and scores the transaction for unusual spending against the user's own "
        "history."
    ),
)
def create_transaction(
    payload: TransactionCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> TransactionOut:
    try:
        transaction = transaction_service.create_transaction(session, user, payload)
        session.commit()
    except transaction_service.TransactionError as exc:
        session.rollback()
        raise bad_request(str(exc)) from exc

    session.refresh(transaction)
    return TransactionOut.model_validate(transaction)


@router.put(
    "/transactions/{transaction_id}",
    response_model=TransactionOut,
    summary="Update a transaction",
    description=(
        "Changing the category records a correction against the stored ML "
        "prediction, which becomes training data on the next model run."
    ),
)
def update_transaction(
    transaction_id: str,
    payload: TransactionUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> TransactionOut:
    transaction = transaction_service.get_transaction(session, user, transaction_id)
    if transaction is None:
        raise not_found("Transaction")

    try:
        updated = transaction_service.update_transaction(session, user, transaction, payload)
        session.commit()
    except transaction_service.TransactionError as exc:
        session.rollback()
        raise bad_request(str(exc)) from exc

    session.refresh(updated)
    return TransactionOut.model_validate(updated)


@router.delete(
    "/transactions/{transaction_id}",
    response_model=Message,
    summary="Delete a transaction",
)
def delete_transaction(
    transaction_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Message:
    transaction = transaction_service.get_transaction(session, user, transaction_id)
    if transaction is None:
        raise not_found("Transaction")

    transaction_service.delete_transaction(session, transaction)
    session.commit()
    return Message(detail="Transaction deleted")


@router.post(
    "/transactions/bulk-delete",
    response_model=Message,
    summary="Delete several transactions",
)
def bulk_delete(
    payload: BulkDeleteRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Message:
    deleted = transaction_service.bulk_delete(session, user, payload.ids)
    session.commit()
    return Message(detail=f"Deleted {deleted} transaction(s)")


@router.post(
    "/transactions/{transaction_id}/anomaly-feedback",
    response_model=TransactionOut,
    summary="Respond to an unusual-spending alert",
    description=(
        "Records whether a flagged transaction was expected. Transactions marked "
        "'expected' or 'ignored' are never re-flagged by later detection runs."
    ),
)
def anomaly_feedback(
    transaction_id: str,
    payload: AnomalyFeedbackRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> TransactionOut:
    transaction = transaction_service.get_transaction(session, user, transaction_id)
    if transaction is None:
        raise not_found("Transaction")

    updated = anomaly_service.apply_feedback(session, transaction, payload.status)
    session.commit()
    session.refresh(updated)
    return TransactionOut.model_validate(updated)


@router.get(
    "/ml/categorizer-status",
    summary="Categorisation model status and feedback-loop statistics",
    description=(
        "Reports whether the model artefact is loaded, when it was trained, and how "
        "often users have accepted or corrected its predictions."
    ),
)
def categorizer_status(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> dict:
    return categorization_service.correction_stats(session, user)
