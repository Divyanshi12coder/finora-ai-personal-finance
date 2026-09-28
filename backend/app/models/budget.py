"""Monthly budgets and their per-category line items.

A ``Budget`` is one month's plan. ``BudgetItem`` rows set a limit per category.
No spent/remaining figures are stored: they are always recomputed from the
transactions table so the numbers cannot drift out of sync with reality.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.user import User


class Budget(Base, TimestampMixin):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "period_month", name="uq_budget_user_period"),
        Index("ix_budgets_user_period", "user_id", "period_month"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Always the first day of the month the budget applies to.
    period_month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    total_limit: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped[User] = relationship(back_populates="budgets")
    items: Mapped[list[BudgetItem]] = relationship(
        back_populates="budget",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BudgetItem.created_at",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Budget {self.name} {self.period_month}>"


class BudgetItem(Base, TimestampMixin):
    __tablename__ = "budget_items"
    __table_args__ = (UniqueConstraint("budget_id", "category_id", name="uq_budget_item_category"),)

    id: Mapped[str] = uuid_pk()
    budget_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    limit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)

    # Set when the limit came from the AI recommendation engine, so the UI can
    # show "suggested by Finora" and the recommendation can be audited.
    recommended_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    recommendation_basis: Mapped[str | None] = mapped_column(Text, nullable=True)

    budget: Mapped[Budget] = relationship(back_populates="items")
    category: Mapped[Category] = relationship(back_populates="budget_items")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BudgetItem {self.category_id} {self.limit_amount}>"
