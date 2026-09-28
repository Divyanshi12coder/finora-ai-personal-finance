"""Financial goals and their contribution ledger.

``current_amount`` is a denormalised running total maintained by the goal
service; every change to it is backed by a ``GoalContribution`` row, so the
balance can always be reconciled against its audit trail.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, uuid_pk
from app.models.enums import GoalStatus

if TYPE_CHECKING:
    from app.models.user import User


class FinancialGoal(Base, TimestampMixin):
    __tablename__ = "financial_goals"
    __table_args__ = (Index("ix_goals_user_status", "user_id", "status"),)

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    goal_type: Mapped[str] = mapped_column(String(40), default="savings", nullable=False)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), nullable=False
    )
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[GoalStatus] = mapped_column(
        Enum(GoalStatus, native_enum=False, length=10), default=GoalStatus.ACTIVE, nullable=False
    )
    icon: Mapped[str] = mapped_column(String(40), default="Target", nullable=False)
    color: Mapped[str] = mapped_column(String(9), default="#0B1F3A", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="goals")
    contributions: Mapped[list[GoalContribution]] = relationship(
        back_populates="goal",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="GoalContribution.occurred_on.desc()",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<FinancialGoal {self.name} {self.current_amount}/{self.target_amount}>"


class GoalContribution(Base, TimestampMixin):
    __tablename__ = "goal_contributions"

    id: Mapped[str] = uuid_pk()
    goal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("financial_goals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Positive to add money, negative to withdraw.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    goal: Mapped[FinancialGoal] = relationship(back_populates="contributions")
