"""Shared model mixins and column helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_uuid() -> str:
    return str(uuid.uuid4())


def uuid_pk() -> Mapped[str]:
    """Primary key column.

    UUIDs rather than serial integers: identifiers appear in API paths, and
    non-enumerable ids remove a whole class of resource-probing attempts (the
    per-user authorisation checks are still enforced server side regardless).
    """
    return mapped_column(String(36), primary_key=True, default=new_uuid)


class TimestampMixin:
    """created_at / updated_at maintained by the ORM."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
