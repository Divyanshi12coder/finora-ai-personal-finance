"""Transactions - the fact table every analytic in Finora is derived from."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    Enum,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, uuid_pk
from app.models.enums import AnomalyStatus, TransactionSource, TransactionType

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.ml_prediction import MLPrediction
    from app.models.receipt import Receipt
    from app.models.user import User


class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"
    __table_args__ = (
        # The three access patterns that matter: date-ranged listing, category
        # roll-ups and merchant roll-ups - all always scoped by user.
        Index("ix_transactions_user_date", "user_id", "occurred_on"),
        Index("ix_transactions_user_category_date", "user_id", "category_id", "occurred_on"),
        Index("ix_transactions_user_merchant", "user_id", "merchant"),
        Index("ix_transactions_user_type_date", "user_id", "type", "occurred_on"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    receipt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("receipts.id", ondelete="SET NULL"), nullable=True
    )

    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        Enum(TransactionType, native_enum=False, length=10), nullable=False
    )
    merchant: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payment_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(JSON, default=list, nullable=True)

    source: Mapped[TransactionSource] = mapped_column(
        Enum(TransactionSource, native_enum=False, length=10),
        default=TransactionSource.MANUAL,
        nullable=False,
    )
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- ML categorisation metadata -----------------------------------------
    ai_categorized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Anomaly detection metadata -----------------------------------------
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    anomaly_status: Mapped[AnomalyStatus] = mapped_column(
        Enum(AnomalyStatus, native_enum=False, length=12),
        default=AnomalyStatus.NONE,
        nullable=False,
        index=True,
    )
    anomaly_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="transactions")
    category: Mapped[Category | None] = relationship(back_populates="transactions")
    receipt: Mapped[Receipt | None] = relationship(
        back_populates="transaction", foreign_keys=[receipt_id]
    )
    predictions: Mapped[list[MLPrediction]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def signed_amount(self) -> Decimal:
        """Income is positive, expense negative. Transfers are neutral."""
        if self.type == TransactionType.INCOME:
            return Decimal(self.amount)
        if self.type == TransactionType.EXPENSE:
            return -Decimal(self.amount)
        return Decimal("0")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Transaction {self.type} {self.amount} {self.merchant}>"
