"""Backend-side wrapper around the trained categorisation model.

This module is intentionally thin: the model, its preprocessing and its
serialisation all live in the repository-root ``ml`` package so the exact same
code path is used at training time and at serving time. Here we only:

* expose a stable API to the services layer,
* apply the confidence policy, and
* degrade gracefully when the artefact is missing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ml.model_store import CategorizerModel, Prediction, get_categorizer, model_info
from ml.preprocessing import build_document

logger = logging.getLogger(__name__)

# Confidence policy
# -----------------
# Below AUTO_APPLY the prediction is still shown, but it is NOT applied silently:
# the transaction is left uncategorised (or the UI asks for confirmation). A
# wrong category quietly corrupts every budget and chart downstream, so the cost
# of a false positive is much higher than the cost of asking.
AUTO_APPLY_THRESHOLD = 0.45
HIGH_CONFIDENCE_THRESHOLD = 0.70


@dataclass
class CategorizationResult:
    available: bool
    category: str | None = None
    confidence: float | None = None
    alternatives: list[tuple[str, float]] = None  # type: ignore[assignment]
    explanation: list[tuple[str, float]] = None  # type: ignore[assignment]
    model_version: str | None = None
    document: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.alternatives is None:
            self.alternatives = []
        if self.explanation is None:
            self.explanation = []

    @property
    def should_auto_apply(self) -> bool:
        return (
            self.available
            and self.category is not None
            and (self.confidence or 0) >= AUTO_APPLY_THRESHOLD
        )

    @property
    def is_high_confidence(self) -> bool:
        return (self.confidence or 0) >= HIGH_CONFIDENCE_THRESHOLD


def get_model() -> CategorizerModel:
    return get_categorizer()


def is_available() -> bool:
    return get_categorizer().is_available


def status() -> dict:
    info = model_info()
    info["auto_apply_threshold"] = AUTO_APPLY_THRESHOLD
    info["high_confidence_threshold"] = HIGH_CONFIDENCE_THRESHOLD
    return info


def categorize(
    description: str | None = None,
    merchant: str | None = None,
    payment_method: str | None = None,
    transaction_type: str | None = None,
    explain: bool = False,
) -> CategorizationResult:
    """Run the classifier over one transaction's text."""
    model = get_model()
    if not model.is_available:
        return CategorizationResult(
            available=False,
            message=(
                "Categorisation model is not trained yet. "
                "Run `python -m ml.train` to enable automatic categorisation."
            ),
        )

    document = build_document(
        description=description,
        merchant=merchant,
        payment_method=payment_method,
        transaction_type=transaction_type,
    )
    if not document:
        return CategorizationResult(
            available=True,
            message="Not enough text on this transaction to categorise it.",
            document="",
        )

    prediction: Prediction | None = model.predict(
        description=description,
        merchant=merchant,
        payment_method=payment_method,
        transaction_type=transaction_type,
    )
    if prediction is None:  # pragma: no cover - guarded by the check above
        return CategorizationResult(available=True, message="No prediction produced.")

    explanation: list[tuple[str, float]] = []
    if explain:
        try:
            explanation = model.explain(document)
        except Exception:  # pragma: no cover - explanation must never break a write
            logger.exception("Failed to build prediction explanation")

    return CategorizationResult(
        available=True,
        category=prediction.category,
        confidence=prediction.confidence,
        alternatives=prediction.alternatives,
        explanation=explanation,
        model_version=prediction.model_version,
        document=document,
    )


def reload_model() -> dict:
    """Hot-reload the artefact after retraining, without restarting the API."""
    get_categorizer(refresh=True)
    logger.info("Categorisation model reloaded from disk")
    return status()
