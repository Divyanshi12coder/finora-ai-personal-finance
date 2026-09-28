"""Transaction and category schemas."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models.enums import (
    AnomalyStatus,
    CategoryKind,
    TransactionSource,
    TransactionType,
)
from app.schemas.common import ORMModel

MAX_AMOUNT = Decimal("99999999.99")


class CategoryOut(ORMModel):
    id: str
    name: str
    kind: CategoryKind
    color: str
    icon: str
    is_system: bool


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: CategoryKind = CategoryKind.EXPENSE
    color: str = Field(default="#0B1F3A", pattern=r"^#(?:[0-9a-fA-F]{3,4}){1,2}$")
    icon: str = Field(default="Wallet", max_length=40)

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Category name cannot be empty")
        return cleaned


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    color: str | None = Field(default=None, pattern=r"^#(?:[0-9a-fA-F]{3,4}){1,2}$")
    icon: str | None = Field(default=None, max_length=40)


class TransactionBase(BaseModel):
    amount: Decimal = Field(
        gt=0, le=MAX_AMOUNT, description="Always positive; direction comes from `type`"
    )
    type: TransactionType
    occurred_on: date
    merchant: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    payment_method: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=12)
    category_id: str | None = None

    @field_validator("occurred_on")
    @classmethod
    def _not_far_future(cls, value: date) -> date:
        # A little future-dating is legitimate (scheduled rent). Years ahead is
        # a typo, and it would wreck every trend chart.
        if (value - date.today()).days > 365:
            raise ValueError("Transaction date cannot be more than a year in the future")
        return value

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for tag in value:
            tag = " ".join(str(tag).split())[:30]
            if tag and tag not in cleaned:
                cleaned.append(tag)
        return cleaned

    @field_validator("merchant", "description", "payment_method", "notes")
    @classmethod
    def _strip(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class TransactionCreate(TransactionBase):
    # When true (and no category_id is supplied) the ML categoriser assigns one.
    auto_categorize: bool = True
    receipt_id: str | None = None


class TransactionUpdate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, le=MAX_AMOUNT)
    type: TransactionType | None = None
    occurred_on: date | None = None
    merchant: str | None = Field(default=None, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    payment_method: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=12)
    category_id: str | None = None
    is_recurring: bool | None = None


class TransactionOut(ORMModel):
    id: str
    amount: Decimal
    type: TransactionType
    occurred_on: date
    merchant: str | None
    description: str | None
    payment_method: str | None
    notes: str | None
    tags: list[str] | None
    category: CategoryOut | None
    source: TransactionSource
    is_recurring: bool
    ai_categorized: bool
    ai_confidence: float | None
    anomaly_status: AnomalyStatus
    anomaly_score: float | None
    anomaly_reason: str | None
    receipt_id: str | None
    created_at: datetime
    updated_at: datetime


class TransactionFilters(BaseModel):
    """Query-string filters for the transaction list endpoint."""

    search: str | None = Field(default=None, max_length=120)
    type: TransactionType | None = None
    category_id: str | None = None
    start: date | None = None
    end: date | None = None
    min_amount: Decimal | None = Field(default=None, ge=0)
    max_amount: Decimal | None = Field(default=None, ge=0)
    payment_method: str | None = Field(default=None, max_length=40)
    anomalies_only: bool = False
    sort_by: str = Field(default="occurred_on")
    sort_dir: str = Field(default="desc", pattern="^(asc|desc)$")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator("sort_by")
    @classmethod
    def _allowed_sort(cls, value: str) -> str:
        # Whitelist, because this value is interpolated into an ORDER BY.
        allowed = {"occurred_on", "amount", "merchant", "created_at"}
        if value not in allowed:
            raise ValueError(f"sort_by must be one of {sorted(allowed)}")
        return value


class CategorizePreviewRequest(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    merchant: str | None = Field(default=None, max_length=160)
    payment_method: str | None = Field(default=None, max_length=40)
    type: TransactionType = TransactionType.EXPENSE


class CategorySuggestion(BaseModel):
    category: str
    confidence: float


class CategorizePreviewResponse(BaseModel):
    available: bool
    category: str | None = None
    category_id: str | None = None
    confidence: float | None = None
    alternatives: list[CategorySuggestion] = Field(default_factory=list)
    explanation: list[dict] = Field(default_factory=list)
    model_version: str | None = None
    message: str | None = None


class AnomalyFeedbackRequest(BaseModel):
    status: AnomalyStatus

    @field_validator("status")
    @classmethod
    def _valid(cls, value: AnomalyStatus) -> AnomalyStatus:
        allowed = {AnomalyStatus.CONFIRMED, AnomalyStatus.EXPECTED, AnomalyStatus.IGNORED}
        if value not in allowed:
            raise ValueError("status must be one of: confirmed, expected, ignored")
        return value


class BulkDeleteRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=200)
