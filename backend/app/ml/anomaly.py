"""Unusual-spending detection.

Two complementary detectors are combined, because each catches a different kind
of "unusual":

1. **Robust z-score (modified z-score, MAD-based)** - per-category amount
   outliers. Uses the median and median absolute deviation rather than mean/std,
   because a single 50x transaction inflates the standard deviation enough to
   hide itself. This detector answers "is this amount unusual *for this
   category*?" and is the one that produces the human-readable range.

2. **Isolation Forest** - multivariate outliers over engineered features
   (log amount, category-relative amount, day of week, day of month, merchant
   familiarity, recency gap). It catches combinations that are individually
   unremarkable: a normal-sized transaction at an unfamiliar merchant on an
   unusual day.

A transaction is flagged when the robust z-score clears its threshold, or when
the Isolation Forest flags it *and* the amount is at least moderately unusual.
Requiring agreement for the ML detector keeps the false-positive rate low -
users stop trusting an alerting feature that cries wolf.

Everything is computed per user, from that user's own history. There is no
global "suspicious over 5000" rule anywhere in this file.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np

logger = logging.getLogger(__name__)

# Minimum history before any detection is attempted. Below this the "normal
# range" is not a range, it is a guess - so we say so instead of flagging.
MIN_TRANSACTIONS = 12
MIN_CATEGORY_TRANSACTIONS = 5

# Modified z-score threshold. 3.5 is the conventional cut-off (Iglewicz & Hoaglin).
ROBUST_Z_THRESHOLD = 3.5
# Isolation Forest agreement threshold - the amount must be at least this
# unusual before a multivariate flag is accepted.
SUPPORTING_Z_THRESHOLD = 2.0
CONTAMINATION = 0.05

# 0.6745 is the 0.75 quantile of the standard normal; it rescales MAD to be a
# consistent estimator of sigma for normally distributed data.
MAD_SCALE = 0.6745


@dataclass
class TransactionFeatures:
    transaction_id: str
    amount: float
    occurred_on: date
    category_id: str | None
    category_name: str
    merchant: str


@dataclass
class AnomalyVerdict:
    transaction_id: str
    is_anomaly: bool
    score: float = 0.0
    reason: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class Baseline:
    """The user's normal spending profile, used to explain every verdict."""

    count: int
    median: float
    mad: float
    p10: float
    p90: float
    typical_low: float
    typical_high: float
    per_category: dict[str, dict]

    def as_dict(self) -> dict:
        return {
            "transactions_analyzed": self.count,
            "median_amount": round(self.median, 2),
            "typical_range_low": round(self.typical_low, 2),
            "typical_range_high": round(self.typical_high, 2),
            "p10": round(self.p10, 2),
            "p90": round(self.p90, 2),
            "categories_profiled": len(self.per_category),
        }


def _robust_z(value: float, median: float, mad: float, values: np.ndarray) -> float:
    """Modified z-score with a fallback when MAD collapses to zero.

    MAD is zero whenever more than half the values are identical (common for
    subscriptions: 199, 199, 199, ...). In that case we fall back to the mean
    absolute deviation, and if that is also zero the series is constant and
    anything different from it is, by definition, unusual.
    """
    if mad > 0:
        return MAD_SCALE * (value - median) / mad

    mean_abs_dev = float(np.mean(np.abs(values - median)))
    if mean_abs_dev > 0:
        return 0.7979 * (value - median) / mean_abs_dev

    return 0.0 if math.isclose(value, median) else math.copysign(10.0, value - median)


def build_baseline(features: list[TransactionFeatures]) -> Baseline:
    amounts = np.array([f.amount for f in features], dtype=float)
    median = float(np.median(amounts))
    mad = float(np.median(np.abs(amounts - median)))

    per_category: dict[str, dict] = {}
    by_category: dict[str, list[float]] = {}
    for item in features:
        by_category.setdefault(item.category_name, []).append(item.amount)

    for name, values in by_category.items():
        arr = np.array(values, dtype=float)
        cat_median = float(np.median(arr))
        cat_mad = float(np.median(np.abs(arr - cat_median)))
        per_category[name] = {
            "count": len(arr),
            "median": cat_median,
            "mad": cat_mad,
            "p10": float(np.percentile(arr, 10)),
            "p90": float(np.percentile(arr, 90)),
            "max": float(arr.max()),
            "values": arr,
        }

    return Baseline(
        count=len(amounts),
        median=median,
        mad=mad,
        p10=float(np.percentile(amounts, 10)),
        p90=float(np.percentile(amounts, 90)),
        typical_low=float(np.percentile(amounts, 10)),
        typical_high=float(np.percentile(amounts, 90)),
        per_category=per_category,
    )


def _engineer_matrix(features: list[TransactionFeatures], baseline: Baseline) -> np.ndarray:
    """Build the numeric feature matrix for the Isolation Forest."""
    merchant_counts: dict[str, int] = {}
    for item in features:
        key = (item.merchant or "").lower()
        merchant_counts[key] = merchant_counts.get(key, 0) + 1

    ordered = sorted(features, key=lambda f: f.occurred_on)
    previous_date: dict[str, date] = {}
    gap_by_id: dict[str, float] = {}
    for item in ordered:
        key = (item.merchant or "").lower()
        prior = previous_date.get(key)
        gap_by_id[item.transaction_id] = float((item.occurred_on - prior).days) if prior else 90.0
        previous_date[key] = item.occurred_on

    rows: list[list[float]] = []
    for item in features:
        category = baseline.per_category.get(item.category_name)
        cat_median = category["median"] if category else baseline.median
        # Ratio to the category norm: 1.0 is typical, 5.0 is five times typical.
        relative = item.amount / cat_median if cat_median > 0 else 1.0
        merchant_familiarity = merchant_counts.get((item.merchant or "").lower(), 0)

        rows.append(
            [
                math.log1p(item.amount),
                min(relative, 50.0),
                float(item.occurred_on.weekday()),
                float(item.occurred_on.day),
                math.log1p(merchant_familiarity),
                math.log1p(min(gap_by_id[item.transaction_id], 365.0)),
            ]
        )
    return np.array(rows, dtype=float)


def _format_range(low: float, high: float) -> str:
    return f"₹{low:,.0f}-₹{high:,.0f}"


def detect(
    features: list[TransactionFeatures],
) -> tuple[list[AnomalyVerdict], Baseline | None, str]:
    """Score every transaction. Returns ``(verdicts, baseline, method)``."""
    if len(features) < MIN_TRANSACTIONS:
        return [], None, "insufficient_data"

    baseline = build_baseline(features)
    verdicts: list[AnomalyVerdict] = []

    # --- Detector 2: Isolation Forest -------------------------------------
    forest_flags: dict[str, float] = {}
    method = "robust_zscore"
    try:
        from sklearn.ensemble import IsolationForest

        matrix = _engineer_matrix(features, baseline)
        forest = IsolationForest(
            n_estimators=200,
            contamination=CONTAMINATION,
            random_state=42,
            n_jobs=1,
        )
        predictions = forest.fit_predict(matrix)
        scores = forest.score_samples(matrix)
        for item, prediction, score in zip(features, predictions, scores, strict=False):
            if prediction == -1:
                forest_flags[item.transaction_id] = float(score)
        method = "isolation_forest+robust_zscore"
    except Exception:  # pragma: no cover - sklearn should always be present
        logger.exception("Isolation Forest failed; falling back to robust z-score only")

    # --- Detector 1: robust z-score, per category -------------------------
    for item in features:
        category = baseline.per_category.get(item.category_name)
        use_category = category is not None and category["count"] >= MIN_CATEGORY_TRANSACTIONS

        if use_category:
            values = category["values"]
            median = category["median"]
            mad = category["mad"]
            scope = item.category_name
            low, high = category["p10"], category["p90"]
        else:
            values = np.array([f.amount for f in features], dtype=float)
            median = baseline.median
            mad = baseline.mad
            scope = "overall"
            low, high = baseline.p10, baseline.p90

        z = _robust_z(item.amount, median, mad, values)
        forest_score = forest_flags.get(item.transaction_id)

        flagged_by_z = z >= ROBUST_Z_THRESHOLD
        flagged_by_forest = forest_score is not None and z >= SUPPORTING_Z_THRESHOLD

        if not (flagged_by_z or flagged_by_forest):
            verdicts.append(
                AnomalyVerdict(
                    transaction_id=item.transaction_id,
                    is_anomaly=False,
                    score=round(float(z), 3),
                )
            )
            continue

        times = item.amount / median if median > 0 else 0
        scope_label = "this category" if use_category else "your spending"
        if flagged_by_z:
            reason = (
                f"₹{item.amount:,.0f} is {times:.1f}x your typical "
                f"{item.category_name} transaction (median ₹{median:,.0f}, "
                f"usual range {_format_range(low, high)})."
            )
            detector = "robust_zscore"
        else:
            reason = (
                f"This transaction stands out across amount, merchant and timing "
                f"compared with {scope_label}. At ₹{item.amount:,.0f} it is "
                f"{times:.1f}x the {item.category_name} median of ₹{median:,.0f}."
            )
            detector = "isolation_forest"

        verdicts.append(
            AnomalyVerdict(
                transaction_id=item.transaction_id,
                is_anomaly=True,
                score=round(float(z), 3),
                reason=reason,
                detail={
                    "detector": detector,
                    "scope": scope,
                    "robust_z": round(float(z), 3),
                    "isolation_forest_score": (
                        round(forest_score, 4) if forest_score is not None else None
                    ),
                    "category_median": round(median, 2),
                    "typical_low": round(low, 2),
                    "typical_high": round(high, 2),
                    "times_median": round(float(times), 2),
                    "comparison_sample_size": int(len(values)),
                    "threshold": ROBUST_Z_THRESHOLD,
                },
            )
        )

    return verdicts, baseline, method


def explain_method() -> str:
    return (
        "Finora compares each expense against your own history, never a fixed "
        "amount. A modified z-score (median + median absolute deviation) finds "
        "amounts that are unusual for that specific category, and an Isolation "
        "Forest over amount, category-relative size, timing, merchant "
        "familiarity and recency finds transactions that are unusual in "
        "combination. A transaction is flagged when the robust z-score exceeds "
        f"{ROBUST_Z_THRESHOLD}, or when the Isolation Forest flags it and the "
        f"amount is at least {SUPPORTING_Z_THRESHOLD} deviations from normal. "
        f"At least {MIN_TRANSACTIONS} transactions are needed before detection runs."
    )
