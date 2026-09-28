"""Data access for transactions.

Every function here takes a ``user_id`` and applies it as a filter. That is the
single most important invariant in the codebase: there is no query path that can
return another user's rows, because none of these helpers accept a query without
the owner.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import AnomalyStatus, Category, Transaction, TransactionType
from app.schemas.transaction import TransactionFilters

SORT_COLUMNS = {
    "occurred_on": Transaction.occurred_on,
    "amount": Transaction.amount,
    "merchant": Transaction.merchant,
    "created_at": Transaction.created_at,
}


def base_query(user_id: str) -> Select:
    return select(Transaction).where(Transaction.user_id == user_id)


def get(session: Session, user_id: str, transaction_id: str) -> Transaction | None:
    stmt = (
        base_query(user_id)
        .where(Transaction.id == transaction_id)
        .options(joinedload(Transaction.category))
    )
    return session.scalars(stmt).first()


def apply_filters(stmt: Select, filters: TransactionFilters) -> Select:
    if filters.search:
        # Parameterised LIKE - the value is bound, never interpolated.
        pattern = f"%{filters.search.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Transaction.merchant).like(pattern),
                func.lower(Transaction.description).like(pattern),
                func.lower(Transaction.notes).like(pattern),
            )
        )
    if filters.type:
        stmt = stmt.where(Transaction.type == filters.type)
    if filters.category_id:
        stmt = stmt.where(Transaction.category_id == filters.category_id)
    if filters.start:
        stmt = stmt.where(Transaction.occurred_on >= filters.start)
    if filters.end:
        stmt = stmt.where(Transaction.occurred_on <= filters.end)
    if filters.min_amount is not None:
        stmt = stmt.where(Transaction.amount >= filters.min_amount)
    if filters.max_amount is not None:
        stmt = stmt.where(Transaction.amount <= filters.max_amount)
    if filters.payment_method:
        stmt = stmt.where(Transaction.payment_method == filters.payment_method)
    if filters.anomalies_only:
        stmt = stmt.where(Transaction.anomaly_status == AnomalyStatus.FLAGGED)
    return stmt


def list_paginated(
    session: Session, user_id: str, filters: TransactionFilters
) -> tuple[list[Transaction], int]:
    stmt = apply_filters(base_query(user_id), filters)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = session.scalar(count_stmt) or 0

    column = SORT_COLUMNS[filters.sort_by]
    order = column.desc() if filters.sort_dir == "desc" else column.asc()

    stmt = (
        stmt.options(joinedload(Transaction.category))
        # Secondary sort keeps pagination stable when many rows share a date.
        .order_by(order, Transaction.created_at.desc(), Transaction.id)
        .offset((filters.page - 1) * filters.page_size)
        .limit(filters.page_size)
    )
    return list(session.scalars(stmt).all()), total


def list_in_range(
    session: Session,
    user_id: str,
    start: date,
    end: date,
    transaction_type: TransactionType | None = None,
    include_transfers: bool = False,
) -> list[Transaction]:
    stmt = base_query(user_id).where(
        Transaction.occurred_on >= start, Transaction.occurred_on <= end
    )
    if transaction_type:
        stmt = stmt.where(Transaction.type == transaction_type)
    elif not include_transfers:
        stmt = stmt.where(Transaction.type != TransactionType.TRANSFER)
    stmt = stmt.options(joinedload(Transaction.category)).order_by(Transaction.occurred_on)
    return list(session.scalars(stmt).all())


def recent(session: Session, user_id: str, limit: int = 8) -> list[Transaction]:
    stmt = (
        base_query(user_id)
        .options(joinedload(Transaction.category))
        .order_by(Transaction.occurred_on.desc(), Transaction.created_at.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt).all())


def sum_by_type(session: Session, user_id: str, start: date, end: date) -> dict[str, Decimal]:
    stmt = (
        select(Transaction.type, func.coalesce(func.sum(Transaction.amount), 0))
        .where(
            Transaction.user_id == user_id,
            Transaction.occurred_on >= start,
            Transaction.occurred_on <= end,
        )
        .group_by(Transaction.type)
    )
    totals = {t.value: Decimal("0") for t in TransactionType}
    for tx_type, total in session.execute(stmt).all():
        key = tx_type.value if hasattr(tx_type, "value") else str(tx_type)
        totals[key] = Decimal(str(total or 0))
    return totals


def sum_by_category(
    session: Session,
    user_id: str,
    start: date,
    end: date,
    transaction_type: TransactionType = TransactionType.EXPENSE,
) -> list[tuple[str | None, str, str, Decimal, int]]:
    """Return ``(category_id, name, color, total, count)`` rows."""
    stmt = (
        select(
            Transaction.category_id,
            func.coalesce(Category.name, "Uncategorised"),
            func.coalesce(Category.color, "#64748B"),
            func.coalesce(func.sum(Transaction.amount), 0),
            func.count(Transaction.id),
        )
        .join(Category, Category.id == Transaction.category_id, isouter=True)
        .where(
            Transaction.user_id == user_id,
            Transaction.type == transaction_type,
            Transaction.occurred_on >= start,
            Transaction.occurred_on <= end,
        )
        .group_by(Transaction.category_id, Category.name, Category.color)
        .order_by(func.coalesce(func.sum(Transaction.amount), 0).desc())
    )
    return [
        (row[0], row[1], row[2], Decimal(str(row[3] or 0)), int(row[4]))
        for row in session.execute(stmt).all()
    ]


def sum_for_category(
    session: Session, user_id: str, category_id: str, start: date, end: date
) -> tuple[Decimal, int]:
    stmt = select(func.coalesce(func.sum(Transaction.amount), 0), func.count(Transaction.id)).where(
        Transaction.user_id == user_id,
        Transaction.category_id == category_id,
        Transaction.type == TransactionType.EXPENSE,
        Transaction.occurred_on >= start,
        Transaction.occurred_on <= end,
    )
    total, count = session.execute(stmt).one()
    return Decimal(str(total or 0)), int(count or 0)


def sum_by_merchant(
    session: Session, user_id: str, start: date, end: date, limit: int = 12
) -> list[tuple[str, Decimal, int, date]]:
    stmt = (
        select(
            Transaction.merchant,
            func.coalesce(func.sum(Transaction.amount), 0),
            func.count(Transaction.id),
            func.max(Transaction.occurred_on),
        )
        .where(
            Transaction.user_id == user_id,
            Transaction.type == TransactionType.EXPENSE,
            Transaction.occurred_on >= start,
            Transaction.occurred_on <= end,
            Transaction.merchant.is_not(None),
            Transaction.merchant != "",
        )
        .group_by(Transaction.merchant)
        .order_by(func.coalesce(func.sum(Transaction.amount), 0).desc())
        .limit(limit)
    )
    return [
        (row[0], Decimal(str(row[1] or 0)), int(row[2]), row[3])
        for row in session.execute(stmt).all()
    ]


def largest_expenses(
    session: Session, user_id: str, start: date, end: date, limit: int = 5
) -> list[Transaction]:
    stmt = (
        base_query(user_id)
        .where(
            Transaction.type == TransactionType.EXPENSE,
            Transaction.occurred_on >= start,
            Transaction.occurred_on <= end,
        )
        .options(joinedload(Transaction.category))
        .order_by(Transaction.amount.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt).all())


def flagged_anomalies(session: Session, user_id: str) -> list[Transaction]:
    stmt = (
        base_query(user_id)
        .where(Transaction.anomaly_status == AnomalyStatus.FLAGGED)
        .options(joinedload(Transaction.category))
        .order_by(Transaction.occurred_on.desc())
    )
    return list(session.scalars(stmt).all())


def count_all(session: Session, user_id: str) -> int:
    return (
        session.scalar(select(func.count(Transaction.id)).where(Transaction.user_id == user_id))
        or 0
    )


def earliest_date(session: Session, user_id: str) -> date | None:
    return session.scalar(
        select(func.min(Transaction.occurred_on)).where(Transaction.user_id == user_id)
    )


def distinct_payment_methods(session: Session, user_id: str) -> list[str]:
    stmt = (
        select(Transaction.payment_method)
        .where(
            Transaction.user_id == user_id,
            Transaction.payment_method.is_not(None),
            Transaction.payment_method != "",
        )
        .distinct()
        .order_by(Transaction.payment_method)
    )
    return [row[0] for row in session.execute(stmt).all()]


def delete_many(session: Session, user_id: str, ids: list[str]) -> int:
    stmt = base_query(user_id).where(Transaction.id.in_(ids))
    rows = list(session.scalars(stmt).all())
    for row in rows:
        session.delete(row)
    session.flush()
    return len(rows)


def merchant_history(
    session: Session, user_id: str, merchant: str, limit: int = 50
) -> list[Transaction]:
    stmt = (
        base_query(user_id)
        .where(
            func.lower(Transaction.merchant) == merchant.lower(),
            Transaction.type == TransactionType.EXPENSE,
        )
        .order_by(Transaction.occurred_on.desc())
        .limit(limit)
    )
    return list(session.scalars(stmt).all())
