"""Receipt / OCR schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.enums import ReceiptStatus
from app.schemas.common import ORMModel
from app.schemas.transaction import CategoryOut

MAX_AMOUNT = Decimal("99999999.99")


class ReceiptItemOut(ORMModel):
    id: str
    line_number: int
    name: str
    quantity: Decimal | None
    unit_price: Decimal | None
    total_price: Decimal | None


class ReceiptItemInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: Decimal | None = Field(default=None, ge=0, le=Decimal("9999"))
    unit_price: Decimal | None = Field(default=None, ge=0, le=MAX_AMOUNT)
    total_price: Decimal | None = Field(default=None, ge=0, le=MAX_AMOUNT)


class ReceiptOut(ORMModel):
    id: str
    original_filename: str
    content_type: str
    file_size: int
    status: ReceiptStatus
    error_message: str | None
    merchant: str | None
    receipt_date: date | None
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal | None
    currency: str
    ocr_engine: str | None
    ocr_confidence: float | None
    processing_ms: int | None
    field_confidence: dict | None
    warnings: list | None
    items: list[ReceiptItemOut]
    suggested_category: CategoryOut | None
    transaction_id: str | None
    raw_text: str | None
    created_at: datetime
    processed_at: datetime | None
    image_url: str


class ReceiptUpdate(BaseModel):
    """User corrections applied before the receipt becomes a transaction."""

    merchant: str | None = Field(default=None, max_length=160)
    receipt_date: date | None = None
    subtotal: Decimal | None = Field(default=None, ge=0, le=MAX_AMOUNT)
    tax: Decimal | None = Field(default=None, ge=0, le=MAX_AMOUNT)
    total: Decimal | None = Field(default=None, ge=0, le=MAX_AMOUNT)
    suggested_category_id: str | None = None
    items: list[ReceiptItemInput] | None = Field(default=None, max_length=100)


class ReceiptConfirmRequest(BaseModel):
    """Convert a (possibly corrected) receipt into a real transaction."""

    merchant: str = Field(min_length=1, max_length=160)
    total: Decimal = Field(gt=0, le=MAX_AMOUNT)
    occurred_on: date
    category_id: str | None = None
    payment_method: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)
    tax: Decimal | None = Field(default=None, ge=0, le=MAX_AMOUNT)
    items: list[ReceiptItemInput] | None = Field(default=None, max_length=100)


class OCRStatusResponse(BaseModel):
    available: bool
    engine: str
    version: str | None = None
    languages: list[str] = Field(default_factory=list)
    message: str
    install_hint: str | None = None
