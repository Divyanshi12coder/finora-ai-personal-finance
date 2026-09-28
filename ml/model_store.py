"""Loading and caching of the persisted categorisation artefact.

Used by both the CLI (``ml.predict``) and the FastAPI backend, so there is one
definition of "what a loaded model looks like".

The loader is deliberately forgiving: if the artefact is missing the backend
must still start and every non-ML feature must keep working. Callers check
``CategorizerModel.is_available``.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ml.paths import CATEGORIZER_MODEL
from ml.pipeline import PIPELINE_VERSION
from ml.preprocessing import build_document

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_CACHE: dict[str, CategorizerModel] = {}


@dataclass
class Prediction:
    """A single categorisation result."""

    category: str
    confidence: float
    alternatives: list[tuple[str, float]] = field(default_factory=list)
    model_version: str = PIPELINE_VERSION
    source: str = "model"

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "confidence": round(self.confidence, 4),
            "alternatives": [
                {"category": name, "confidence": round(score, 4)}
                for name, score in self.alternatives
            ],
            "model_version": self.model_version,
            "source": self.source,
        }


@dataclass
class CategorizerModel:
    """Wrapper around the fitted scikit-learn pipeline."""

    pipeline: Any | None
    labels: list[str]
    pipeline_version: str | None
    trained_at: str | None
    path: Path
    error: str | None = None

    @property
    def is_available(self) -> bool:
        return self.pipeline is not None

    def predict(
        self,
        description: str | None = None,
        merchant: str | None = None,
        payment_method: str | None = None,
        transaction_type: str | None = None,
        top_k: int = 3,
    ) -> Prediction | None:
        """Predict a category. Returns ``None`` when no model is loaded."""
        if self.pipeline is None:
            return None

        document = build_document(
            description=description,
            merchant=merchant,
            payment_method=payment_method,
            transaction_type=transaction_type,
        )
        if not document:
            return None

        probabilities = self.pipeline.predict_proba([document])[0]
        classes = list(self.pipeline.classes_)
        ranked = sorted(
            zip(classes, probabilities, strict=False), key=lambda item: item[1], reverse=True
        )

        best_category, best_score = ranked[0]
        return Prediction(
            category=str(best_category),
            confidence=float(best_score),
            alternatives=[(str(name), float(score)) for name, score in ranked[1:top_k]],
            model_version=self.pipeline_version or PIPELINE_VERSION,
        )

    def explain(self, document: str, top_k: int = 6) -> list[tuple[str, float]]:
        """Return the tokens that pushed the prediction toward its class.

        Linear models make this cheap and honest: the contribution of a feature
        is ``tfidf_value * coefficient`` for the predicted class.
        """
        if self.pipeline is None or not document:
            return []
        features = self.pipeline.named_steps["features"]
        classifier = self.pipeline.named_steps["classifier"]
        vector = features.transform([document])
        names = features.get_feature_names_out()
        predicted = classifier.predict(vector)[0]
        class_index = list(classifier.classes_).index(predicted)
        coefficients = classifier.coef_[class_index]

        contributions: list[tuple[str, float]] = []
        rows, cols = vector.nonzero()
        for col in cols:
            contribution = float(vector[0, col] * coefficients[col])
            if contribution > 0:
                contributions.append((str(names[col]).split("__", 1)[-1], contribution))
        contributions.sort(key=lambda item: item[1], reverse=True)
        return contributions[:top_k]


def _load(path: Path) -> CategorizerModel:
    if not path.exists():
        message = (
            f"Categorisation model not found at {path}. " "Run `python -m ml.train` to create it."
        )
        logger.warning(message)
        return CategorizerModel(None, [], None, None, path, error=message)

    try:
        import joblib

        artefact = joblib.load(path)
        version = artefact.get("pipeline_version")
        if version != PIPELINE_VERSION:
            logger.warning(
                "Model artefact version %s does not match expected %s; retrain recommended.",
                version,
                PIPELINE_VERSION,
            )
        trained_at = artefact.get("trained_at")
        logger.info("Loaded categorisation model (version=%s, trained_at=%s)", version, trained_at)
        return CategorizerModel(
            pipeline=artefact["pipeline"],
            labels=list(artefact.get("labels") or []),
            pipeline_version=version,
            trained_at=trained_at,
            path=path,
        )
    except Exception as exc:  # pragma: no cover - defensive
        message = f"Failed to load categorisation model from {path}: {exc}"
        logger.exception(message)
        return CategorizerModel(None, [], None, None, path, error=message)


def get_categorizer(path: Path = CATEGORIZER_MODEL, refresh: bool = False) -> CategorizerModel:
    """Return the cached model, loading it on first use."""
    key = str(path)
    with _LOCK:
        if refresh or key not in _CACHE:
            _CACHE[key] = _load(path)
        return _CACHE[key]


def model_info(path: Path = CATEGORIZER_MODEL) -> dict[str, Any]:
    model = get_categorizer(path)
    trained_at = model.trained_at
    age_days: float | None = None
    if trained_at:
        try:
            parsed = datetime.fromisoformat(trained_at)
            age_days = round((datetime.now(parsed.tzinfo) - parsed).total_seconds() / 86400, 2)
        except ValueError:  # pragma: no cover - defensive
            age_days = None
    return {
        "available": model.is_available,
        "pipeline_version": model.pipeline_version,
        "trained_at": trained_at,
        "age_days": age_days,
        "labels": model.labels,
        "path": str(model.path),
        "error": model.error,
    }
