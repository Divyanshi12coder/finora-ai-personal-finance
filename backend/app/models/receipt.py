"""Uploaded receipts and the structured fields extracted from them.

Both the raw OCR text and the parsed fields are persisted. Keeping the raw text
means a parsing bug can be diagnosed (and the parser improved) without asking
the user to re-upload the image.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, uuid_pk
from app.models.enums import ReceiptStatus

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.transaction import Transaction
    from app.models.user import User


class Receipt(Base, TimestampMixin):
    __tablename__ = "receipts"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # --- Stored file ---------------------------------------------------------
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[ReceiptStatus] = mapped_column(
        Enum(ReceiptStatus, native_enum=False, length=12),
        default=ReceiptStatus.UPLOADED,
        nullable=False,
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- OCR output ----------------------------------------------------------
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_engine: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Parsed fields -------------------------------------------------------
    merchant: Mapped[str | None] = mapped_column(String(160), nullable=True)
    receipt_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    tax: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)

    suggested_category_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    # Per-field extraction confidence + human-readable warnings, so the UI can
    # highlight exactly which values need checking.
    field_confidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)

    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    user: Mapped[User] = relationship(back_populates="receipts")
    items: Mapped[list[ReceiptItem]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ReceiptItem.line_number",
    )
    suggested_category: Mapped[Category | None] = relationship(foreign_keys=[suggested_category_id])
    transaction: Mapped[Transaction | None] = relationship(
        back_populates="receipt",
        primaryjoin="Receipt.id == Transaction.receipt_id",
        uselist=False,
        viewonly=True,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Receipt {self.original_filename} {self.status}>"


class ReceiptItem(Base, TimestampMixin):
    __tablename__ = "receipt_items"

    id: Mapped[str] = uuid_pk()
    receipt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False, index=True
    )

    line_number: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    receipt: Mapped[Receipt] = relationship(back_populates="items")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ReceiptItem {self.name} {self.total_price}>"
