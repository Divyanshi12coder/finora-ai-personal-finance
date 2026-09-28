"""Evaluate the persisted categorisation model.

    python -m ml.evaluate

Unlike ``ml.train`` this does not refit anything: it loads the artefact that the
backend actually serves and scores it against a held-out split of the current
dataset, so you can detect a stale model after the dataset grows with user
corrections.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import train_test_split

from ml.dataset import load_dataset
from ml.model_store import get_categorizer
from ml.paths import CATEGORIZER_METRICS


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the persisted Finora model")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    model = get_categorizer(refresh=True)
    if not model.is_available:
        print(f"ERROR: {model.error}", file=sys.stderr)
        return 1

    dataset = load_dataset()
    X = np.array(dataset.documents, dtype=object)
    y = np.array(dataset.labels, dtype=object)
    _, X_test, _, y_test = train_test_split(
        X, y, test_size=args.test_size, random_state=args.random_state, stratify=y
    )

    y_pred = model.pipeline.predict(X_test)
    labels_sorted = sorted(set(dataset.labels))

    report = {
        "model_trained_at": model.trained_at,
        "model_version": model.pipeline_version,
        "evaluated_examples": int(len(X_test)),
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision_macro": float(precision_score(y_test, y_pred, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y_test, y_pred, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y_test, y_pred, average="macro", zero_division=0)),
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    print("=" * 72)
    print("Finora - evaluation of the persisted categorisation model")
    print("=" * 72)
    print(f"model trained at : {model.trained_at}")
    print(f"model version    : {model.pipeline_version}")
    print(f"evaluated on     : {len(X_test)} held-out examples")
    print()
    print(f"accuracy         : {report['accuracy']:.4f}")
    print(f"precision (macro): {report['precision_macro']:.4f}")
    print(f"recall (macro)   : {report['recall_macro']:.4f}")
    print(f"f1 (macro)       : {report['f1_macro']:.4f}")
    print()
    print(classification_report(y_test, y_pred, zero_division=0))
    print("Confusion matrix (rows = true, cols = predicted):")
    matrix = confusion_matrix(y_test, y_pred, labels=labels_sorted)
    width = max(len(label) for label in labels_sorted) + 2
    print(" " * width + "".join(f"{label[:6]:>8}" for label in labels_sorted))
    for label, row in zip(labels_sorted, matrix, strict=False):
        print(f"{label:<{width}}" + "".join(f"{int(v):>8}" for v in row))

    if CATEGORIZER_METRICS.exists():
        print(f"\nTraining-time metrics report: {CATEGORIZER_METRICS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
