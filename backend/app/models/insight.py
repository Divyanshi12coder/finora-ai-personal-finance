"""Generated financial insights.

The ``data`` column holds the structured facts the insight engine computed
(amounts, percentages, period boundaries). ``ai_explanation`` holds the optional
natural-language rendering. The split is deliberate and is the core of Finora's
AI design: the backend owns the numbers, the AI only phrases them.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Date, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, uuid_pk
from app.models.enums import InsightSeverity, InsightType

if TYPE_CHECKING:
    from app.models.user import User


class Insight(Base, TimestampMixin):
    __tablename__ = "insights"
    __table_args__ = (
        Index("ix_insights_user_created", "user_id", "created_at"),
        Index("ix_insights_user_type", "user_id", "type"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    type: Mapped[InsightType] = mapped_column(
        Enum(InsightType, native_enum=False, length=30), nullable=False
    )
    severity: Mapped[InsightSeverity] = mapped_column(
        Enum(InsightSeverity, native_enum=False, length=10),
        default=InsightSeverity.INFO,
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured, machine-checkable facts behind the insight.
    data: Mapped[dict | None] = mapped_column(JSON, default=dict, nullable=True)

    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Stable key used to avoid inserting the same insight twice per period.
    fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship(back_populates="insights")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Insight {self.type} {self.title}>"
