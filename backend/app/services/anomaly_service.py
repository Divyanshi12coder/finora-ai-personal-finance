"""Anomaly detection orchestration.

Bridges the pure-numeric detector in ``app.ml.anomaly`` with the database:
loads a user's history, runs detection, persists the verdicts, and honours the
user's feedback (a transaction marked "expected" is never re-flagged).
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.ml import anomaly as detector
from app.models import AnomalyStatus, Transaction, TransactionType, User
from app.repositories import transaction_repository as repo

logger = logging.getLogger(__name__)

# How far back to build the behavioural baseline.
LOOKBACK_DAYS = 365
# Only transactions within this window get *newly* flagged; older ones still
# inform the baseline. Alerting someone about a transaction from eight months
# ago is noise.
FLAG_WINDOW_DAYS = 90

# Statuses the user has explicitly resolved - never re-flag these.
USER_RESOLVED = {AnomalyStatus.CONFIRMED, AnomalyStatus.EXPECTED, AnomalyStatus.IGNORED}


def _to_features(transactions: list[Transaction]) -> list[detector.TransactionFeatures]:
    return [
        detector.TransactionFeatures(
            transaction_id=t.id,
            amount=float(t.amount),
            occurred_on=t.occurred_on,
            category_id=t.category_id,
            category_name=t.category.name if t.category else "Uncategorised",
            merchant=t.merchant or "unknown",
        )
        for t in transactions
    ]


def _history(session: Session, user: User, today: date | None = None) -> list[Transaction]:
    today = today or date.today()
    start = today - timedelta(days=LOOKBACK_DAYS)
    return repo.list_in_range(
        session, user.id, start, today, transaction_type=TransactionType.EXPENSE
    )


def run_detection(
    session: Session, user: User, today: date | None = None, persist: bool = True
) -> dict:
    """Run detection across the user's history and persist the verdicts."""
    today = today or date.today()
    transactions = _history(session, user, today)

    if len(transactions) < detector.MIN_TRANSACTIONS:
        return {
            "sufficient_data": False,
            "message": (
                f"Unusual-spending detection needs at least "
                f"{detector.MIN_TRANSACTIONS} expenses to learn what is normal for "
                f"you. You have {len(transactions)} so far."
            ),
            "method": "insufficient_data",
            "analyzed_transactions": len(transactions),
            "anomalies": [],
            "baseline": {},
            "explanation": detector.explain_method(),
        }

    verdicts, baseline, method = detector.detect(_to_features(transactions))
    by_id = {t.id: t for t in transactions}
    verdict_by_id = {v.transaction_id: v for v in verdicts}
    flag_cutoff = today - timedelta(days=FLAG_WINDOW_DAYS)

    anomalies: list[dict] = []
    for verdict in verdicts:
        transaction = by_id.get(verdict.transaction_id)
        if transaction is None:  # pragma: no cover - defensive
            continue

        # The user already told us what they think about this one.
        if transaction.anomaly_status in USER_RESOLVED:
            if transaction.anomaly_status == AnomalyStatus.CONFIRMED:
                anomalies.append(
                    {
                        "transaction": transaction,
                        "score": transaction.anomaly_score or verdict.score,
                        "reason": transaction.anomaly_reason or verdict.reason,
                        "detail": verdict.detail,
                    }
                )
            continue

        if persist:
            transaction.anomaly_score = verdict.score

        if verdict.is_anomaly and transaction.occurred_on >= flag_cutoff:
            if persist:
                transaction.anomaly_status = AnomalyStatus.FLAGGED
                transaction.anomaly_reason = verdict.reason
            anomalies.append(
                {
                    "transaction": transaction,
                    "score": verdict.score,
                    "reason": verdict.reason,
                    "detail": verdict.detail,
                }
            )
        elif persist and transaction.anomaly_status == AnomalyStatus.FLAGGED:
            # No longer unusual (the baseline moved) - clear the stale flag.
            transaction.anomaly_status = AnomalyStatus.NONE
            transaction.anomaly_reason = None

    if persist:
        session.flush()

    anomalies.sort(key=lambda a: a["score"], reverse=True)
    logger.info(
        "Anomaly detection for user %s: %d/%d flagged via %s",
        user.id,
        len(anomalies),
        len(transactions),
        method,
    )

    return {
        "sufficient_data": True,
        "message": None,
        "method": method,
        "analyzed_transactions": len(transactions),
        "anomalies": anomalies,
        "baseline": baseline.as_dict() if baseline else {},
        "explanation": detector.explain_method(),
        "_verdicts": verdict_by_id,
    }


def score_single_transaction(session: Session, user: User, transaction: Transaction) -> None:
    """Score one newly created/updated transaction against existing history.

    Called on the write path so a user sees the flag immediately rather than
    waiting for the next full sweep. The baseline deliberately excludes the new
    transaction itself - otherwise a large outlier partly normalises itself.
    """
    if transaction.type != TransactionType.EXPENSE:
        return
    if transaction.anomaly_status in USER_RESOLVED:
        return

    history = [t for t in _history(session, user) if t.id != transaction.id]
    if len(history) < detector.MIN_TRANSACTIONS:
        return

    features = _to_features([*history, transaction])
    verdicts, _, _ = detector.detect(features)
    verdict = next((v for v in verdicts if v.transaction_id == transaction.id), None)
    if verdict is None:  # pragma: no cover - defensive
        return

    transaction.anomaly_score = verdict.score
    if verdict.is_anomaly:
        transaction.anomaly_status = AnomalyStatus.FLAGGED
        transaction.anomaly_reason = verdict.reason
        logger.info("Transaction %s flagged as unusual: %s", transaction.id, verdict.reason)
    else:
        transaction.anomaly_status = AnomalyStatus.NONE
        transaction.anomaly_reason = None
    session.flush()


def apply_feedback(
    session: Session, transaction: Transaction, status: AnomalyStatus
) -> Transaction:
    """Record the user's judgement on a flagged transaction."""
    transaction.anomaly_status = status
    if status == AnomalyStatus.EXPECTED:
        transaction.anomaly_reason = "Marked as expected by you - similar amounts won't be flagged."
    elif status == AnomalyStatus.IGNORED:
        transaction.anomaly_reason = "Alert dismissed by you."
    session.flush()
    logger.info("Anomaly feedback for %s: %s", transaction.id, status.value)
    return transaction


def count_flagged(session: Session, user: User) -> int:
    return len(repo.flagged_anomalies(session, user.id))
