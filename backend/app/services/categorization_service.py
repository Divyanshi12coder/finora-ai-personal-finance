"""Categorisation orchestration and the ML feedback loop.

Responsibilities:

* run the classifier for a transaction and map the predicted label to a real
  Category row,
* log every prediction to ``ml_predictions`` for auditability,
* record when a user overrides a prediction, and
* export those corrections as training rows.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml import categorizer
from app.models import Category, MLPrediction, Transaction, User
from app.services import category_service

logger = logging.getLogger(__name__)


def predict_for_transaction(
    session: Session,
    user: User,
    description: str | None,
    merchant: str | None,
    payment_method: str | None,
    transaction_type: str | None,
    explain: bool = False,
) -> tuple[categorizer.CategorizationResult, Category | None]:
    """Predict a category and resolve it to a Category row the user can use."""
    result = categorizer.categorize(
        description=description,
        merchant=merchant,
        payment_method=payment_method,
        transaction_type=transaction_type,
        explain=explain,
    )
    if not result.category:
        return result, None

    category = category_service.get_by_name(session, user, result.category)
    if category is None:
        # The model knows a label that has no matching row (e.g. the system
        # categories were edited). Log it rather than inventing a category.
        logger.warning(
            "Model predicted category %r which has no matching Category row", result.category
        )
    return result, category


def log_prediction(
    session: Session,
    user: User,
    result: categorizer.CategorizationResult,
    transaction: Transaction | None,
    final_category_name: str | None,
    description: str | None,
    merchant: str | None,
    payment_method: str | None,
    transaction_type: str | None,
) -> MLPrediction | None:
    """Record a prediction (and whether the user immediately overrode it)."""
    if not result.available or not result.category:
        return None

    was_corrected = bool(final_category_name and final_category_name != result.category)
    record = MLPrediction(
        user_id=user.id,
        transaction_id=transaction.id if transaction else None,
        model_name="categorizer",
        model_version=result.model_version,
        input_document=result.document,
        input_description=description,
        input_merchant=merchant,
        input_payment_method=payment_method,
        input_transaction_type=transaction_type,
        predicted_category=result.category,
        confidence=result.confidence,
        alternatives=[
            {"category": name, "confidence": round(score, 4)}
            for name, score in (result.alternatives or [])
        ],
        final_category=final_category_name,
        was_corrected=was_corrected,
    )
    session.add(record)
    session.flush()
    return record


def record_correction(
    session: Session, user: User, transaction: Transaction, new_category: Category | None
) -> None:
    """Mark the stored prediction as corrected when a user changes a category.

    Called on every transaction update where the category changed. If there is
    no prediction for this transaction (e.g. it was categorised manually from
    the start) nothing is recorded - only genuine overrides of a model output
    become training data.
    """
    stmt = (
        select(MLPrediction)
        .where(
            MLPrediction.transaction_id == transaction.id,
            MLPrediction.user_id == user.id,
        )
        .order_by(MLPrediction.created_at.desc())
        .limit(1)
    )
    prediction = session.scalars(stmt).first()
    if prediction is None:
        return

    final_name = new_category.name if new_category else None
    prediction.final_category = final_name
    prediction.was_corrected = bool(final_name and final_name != prediction.predicted_category)
    session.flush()

    if prediction.was_corrected:
        logger.info(
            "Categorisation correction recorded: %s -> %s (confidence was %.3f)",
            prediction.predicted_category,
            final_name,
            prediction.confidence or 0.0,
        )


def correction_stats(session: Session, user: User | None = None) -> dict:
    """Summary of how the model is performing against real user behaviour."""
    stmt = select(MLPrediction)
    if user is not None:
        stmt = stmt.where(MLPrediction.user_id == user.id)
    predictions = list(session.scalars(stmt).all())

    total = len(predictions)
    corrected = sum(1 for p in predictions if p.was_corrected)
    accepted = total - corrected
    confidences = [p.confidence for p in predictions if p.confidence is not None]

    return {
        "total_predictions": total,
        "accepted": accepted,
        "corrected": corrected,
        "acceptance_rate": round(accepted / total, 4) if total else None,
        "mean_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
        "pending_training_examples": corrected,
        "model": categorizer.status(),
    }


def collect_training_corrections(session: Session) -> list[dict[str, str]]:
    """Return corrected predictions as rows ready for ``ml/datasets/corrections.csv``.

    Deliberately minimal: only the text fields needed to learn from, never
    amounts or user identifiers.
    """
    stmt = select(MLPrediction).where(
        MLPrediction.was_corrected.is_(True),
        MLPrediction.final_category.is_not(None),
    )
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for prediction in session.scalars(stmt).all():
        description = (prediction.input_description or "").strip()
        merchant = (prediction.input_merchant or "").strip()
        category = (prediction.final_category or "").strip()
        if not category or (not description and not merchant):
            continue

        key = (description.lower(), merchant.lower(), category)
        if key in seen:
            continue
        seen.add(key)

        rows.append(
            {
                "description": description,
                "merchant": merchant,
                "payment_method": (prediction.input_payment_method or "").strip(),
                "transaction_type": (prediction.input_transaction_type or "expense").strip(),
                "category": category,
            }
        )
    return rows
