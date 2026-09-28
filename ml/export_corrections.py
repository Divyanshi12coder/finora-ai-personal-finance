"""Export user categorisation corrections from the database into the ML dataset.

    python -m ml.export_corrections
    python -m ml.export_corrections --min-count 10

This is the bridge that closes the feedback loop:

    user overrides a prediction in the UI
        -> backend stores an MLPrediction row with was_corrected = true
        -> this script exports those rows to ml/datasets/corrections.csv
        -> `python -m ml.train` folds them into the next model

Only corrected predictions are exported, and only the fields needed for
training - no amounts, no user identifiers, no free-text notes. The export is
deliberately minimal so that retraining data carries as little personal
information as possible.
"""

from __future__ import annotations

import argparse
import csv
import sys

from ml.paths import CORRECTIONS_DATASET, ensure_dirs


def main() -> int:
    parser = argparse.ArgumentParser(description="Export user corrections for retraining")
    parser.add_argument(
        "--min-count",
        type=int,
        default=1,
        help="Refuse to write the CSV unless at least this many corrections exist",
    )
    args = parser.parse_args()

    # Imported lazily so the ML package does not hard-depend on the backend.
    try:
        from app.database import session_scope
        from app.services.categorization_service import collect_training_corrections
    except ImportError as exc:  # pragma: no cover - environment dependent
        print(
            "ERROR: backend package not importable. Run this from the repository "
            f"root with PYTHONPATH including `backend/` ({exc})",
            file=sys.stderr,
        )
        return 1

    ensure_dirs()
    with session_scope() as session:
        rows = collect_training_corrections(session)

    if len(rows) < args.min_count:
        print(
            f"Only {len(rows)} corrections available (min-count={args.min_count}); "
            "nothing written."
        )
        return 0

    fieldnames = ["description", "merchant", "payment_method", "transaction_type", "category"]
    with CORRECTIONS_DATASET.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Exported {len(rows)} corrections -> {CORRECTIONS_DATASET}")
    print("Run `python -m ml.train` to fold them into the model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
