"""User account and onboarding profile."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, uuid_pk
from app.models.enums import BudgetingPreference

if TYPE_CHECKING:
    from app.models.ai import AIConversation
    from app.models.budget import Budget
    from app.models.category import Category
    from app.models.goal import FinancialGoal
    from app.models.insight import Insight
    from app.models.receipt import Receipt
    from app.models.transaction import Transaction


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = uuid_pk()

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Onboarding profile --------------------------------------------------
    currency: Mapped[str] = mapped_column(String(3), default="INR", nullable=False)
    monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    income_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    typical_monthly_expenses: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    savings_goal_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    emergency_fund_target: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    budgeting_preference: Mapped[BudgetingPreference] = mapped_column(
        Enum(BudgetingPreference, native_enum=False, length=20),
        default=BudgetingPreference.BALANCED,
        nullable=False,
    )
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Password reset ------------------------------------------------------
    # Only a hash of the reset token is stored, so a database leak cannot be
    # replayed to take over accounts.
    reset_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Relationships -------------------------------------------------------
    transactions: Mapped[list[Transaction]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    categories: Mapped[list[Category]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    budgets: Mapped[list[Budget]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    goals: Mapped[list[FinancialGoal]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    receipts: Mapped[list[Receipt]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    insights: Mapped[list[Insight]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    conversations: Mapped[list[AIConversation]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.email}>"
