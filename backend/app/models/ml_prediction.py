"""Audit log of every ML categorisation, including user corrections.

This table is what turns the classifier from a one-shot model into a system
that improves: rows with ``was_corrected = True`` are exported by
``python -m ml.export_corrections`` and become training data on the next run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from app.models.transaction import Transaction


class MLPrediction(Base, TimestampMixin):
    __tablename__ = "ml_predictions"
    __table_args__ = (
        Index("ix_predictions_user_corrected", "user_id", "was_corrected"),
        Index("ix_predictions_model", "model_name", "model_version"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True, index=True
    )

    model_name: Mapped[str] = mapped_column(String(60), default="categorizer", nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # The exact normalised document fed to the vectoriser - reproducing a
    # prediction later requires the input, not just the output.
    input_document: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Raw fields kept so corrections can be exported as training rows.
    input_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_merchant: Mapped[str | None] = mapped_column(String(160), nullable=True)
    input_payment_method: Mapped[str | None] = mapped_column(String(40), nullable=True)
    input_transaction_type: Mapped[str | None] = mapped_column(String(10), nullable=True)

    predicted_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    alternatives: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)

    final_category: Mapped[str | None] = mapped_column(String(60), nullable=True)
    was_corrected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    transaction: Mapped[Transaction | None] = relationship(back_populates="predictions")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MLPrediction {self.predicted_category} -> {self.final_category}>"
