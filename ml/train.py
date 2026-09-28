"""Train and persist the transaction categorisation model.

    python -m ml.train
    python -m ml.train --no-corrections      # seed data only
    python -m ml.train --test-size 0.25

Steps performed (in order):

1. Load the seed dataset plus any exported user corrections.
2. Normalise/compose the text documents (``ml.preprocessing``).
3. Stratified train/test split.
4. Fit the TF-IDF + Logistic Regression pipeline.
5. Evaluate on the held-out split and via 5-fold cross-validation.
6. Print accuracy / precision / recall / F1 and the confusion matrix.
7. Persist the fitted pipeline and a JSON metrics report.

Metrics printed by this script are computed, never hard-coded. The README
documents the methodology rather than baking in numbers that could drift.
"""

from __future__ import annotations

import argparse
import json
import platform
from datetime import UTC, datetime

import joblib
import numpy as np
import sklearn
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split

from ml.dataset import load_dataset
from ml.paths import CATEGORIZER_METRICS, CATEGORIZER_MODEL, ensure_dirs
from ml.pipeline import PIPELINE_VERSION, build_pipeline


def _format_confusion_matrix(matrix: np.ndarray, labels: list[str]) -> str:
    width = max(len(label) for label in labels) + 2
    header = " " * width + "".join(f"{label[:6]:>8}" for label in labels)
    lines = [header]
    for label, row in zip(labels, matrix, strict=False):
        cells = "".join(f"{int(value):>8}" for value in row)
        lines.append(f"{label:<{width}}{cells}")
    return "\n".join(lines)


def train(
    test_size: float = 0.2,
    random_state: int = 42,
    include_corrections: bool = True,
    cross_validate: bool = True,
) -> dict:
    ensure_dirs()

    print("=" * 72)
    print("Finora - transaction categorisation training")
    print("=" * 72)

    dataset = load_dataset(include_corrections=include_corrections)
    labels_sorted = sorted(set(dataset.labels))
    print("\n[1/6] Dataset loaded")
    print(f"      total examples      : {len(dataset)}")
    print(f"      seed examples       : {dataset.seed_count}")
    print(f"      user corrections    : {dataset.correction_count} (weighted)")
    print(f"      categories          : {len(labels_sorted)} -> {', '.join(labels_sorted)}")

    if len(dataset) < 50:
        print("\n      WARNING: fewer than 50 examples. Metrics below are indicative only.")

    X = np.array(dataset.documents, dtype=object)
    y = np.array(dataset.labels, dtype=object)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )
    print(f"\n[2/6] Split: {len(X_train)} train / {len(X_test)} test (stratified)")

    pipeline = build_pipeline(random_state=random_state)
    print("\n[3/6] Fitting TF-IDF(word 1-2 + char_wb 3-5) -> LogisticRegression ...")
    pipeline.fit(X_train, y_train)

    n_features = len(pipeline.named_steps["features"].get_feature_names_out())
    print(f"      vocabulary size     : {n_features} features")

    print("\n[4/6] Held-out evaluation")
    y_pred = pipeline.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, average="macro", zero_division=0)
    recall = recall_score(y_test, y_pred, average="macro", zero_division=0)
    f1 = f1_score(y_test, y_pred, average="macro", zero_division=0)

    print(f"      accuracy            : {accuracy:.4f}")
    print(f"      precision (macro)   : {precision:.4f}")
    print(f"      recall (macro)      : {recall:.4f}")
    print(f"      f1 (macro)          : {f1:.4f}")
    print()
    print(classification_report(y_test, y_pred, zero_division=0))

    matrix = confusion_matrix(y_test, y_pred, labels=labels_sorted)
    print("Confusion matrix (rows = true, cols = predicted):")
    print(_format_confusion_matrix(matrix, labels_sorted))

    cv_mean: float | None = None
    cv_std: float | None = None
    if cross_validate:
        print("\n[5/6] 5-fold stratified cross-validation ...")
        skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state)
        scores = cross_val_score(
            build_pipeline(random_state=random_state), X, y, cv=skf, scoring="f1_macro"
        )
        cv_mean = float(scores.mean())
        cv_std = float(scores.std())
        print(f"      f1_macro per fold   : {', '.join(f'{s:.4f}' for s in scores)}")
        print(f"      f1_macro mean       : {cv_mean:.4f} (+/- {cv_std:.4f})")
    else:
        print("\n[5/6] Cross-validation skipped")

    # Refit on the full dataset so the shipped model uses every labelled example.
    final_pipeline = build_pipeline(random_state=random_state)
    final_pipeline.fit(X, y)

    metrics = {
        "pipeline_version": PIPELINE_VERSION,
        "trained_at": datetime.now(UTC).isoformat(),
        "sklearn_version": sklearn.__version__,
        "python_version": platform.python_version(),
        "dataset": {
            "total_examples": len(dataset),
            "seed_examples": dataset.seed_count,
            "correction_examples": dataset.correction_count,
            "categories": labels_sorted,
            "note": (
                "Seed rows are synthetic demonstration data generated by "
                "ml.build_dataset from real merchant names and real bank narration "
                "templates. Correction rows are genuine user labels exported from "
                "the application database."
            ),
        },
        "split": {"test_size": test_size, "random_state": random_state},
        "holdout": {
            "accuracy": float(accuracy),
            "precision_macro": float(precision),
            "recall_macro": float(recall),
            "f1_macro": float(f1),
        },
        "cross_validation": {
            "folds": 5,
            "scoring": "f1_macro",
            "mean": cv_mean,
            "std": cv_std,
        },
        "per_class": classification_report(y_test, y_pred, zero_division=0, output_dict=True),
        "confusion_matrix": {
            "labels": labels_sorted,
            "matrix": matrix.tolist(),
        },
        "n_features": int(n_features),
    }

    artefact = {
        "pipeline": final_pipeline,
        "labels": labels_sorted,
        "pipeline_version": PIPELINE_VERSION,
        "trained_at": metrics["trained_at"],
        "metrics": metrics["holdout"],
    }

    joblib.dump(artefact, CATEGORIZER_MODEL)
    CATEGORIZER_METRICS.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print(f"\n[6/6] Saved model   -> {CATEGORIZER_MODEL}")
    print(f"      Saved metrics -> {CATEGORIZER_METRICS}")
    print("\nDone.")
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the Finora categorisation model")
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument(
        "--no-corrections",
        action="store_true",
        help="Train on the seed dataset only, ignoring exported user corrections",
    )
    parser.add_argument("--no-cv", action="store_true", help="Skip cross-validation")
    args = parser.parse_args()

    train(
        test_size=args.test_size,
        random_state=args.random_state,
        include_corrections=not args.no_corrections,
        cross_validate=not args.no_cv,
    )


if __name__ == "__main__":
    main()
