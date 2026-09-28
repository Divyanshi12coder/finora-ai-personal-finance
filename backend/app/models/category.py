"""Transaction categories.

A category with ``user_id IS NULL`` is a system category available to everyone
(Food, Transport, ...). A category with a ``user_id`` is a custom category owned
by that user. The unique constraint is scoped per user so two users may both
create "Pet Care" without colliding.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, uuid_pk
from app.models.enums import CategoryKind

if TYPE_CHECKING:
    from app.models.budget import BudgetItem
    from app.models.transaction import Transaction
    from app.models.user import User


class Category(Base, TimestampMixin):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_category_user_name"),
        Index("ix_categories_user_kind", "user_id", "kind"),
    )

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(60), nullable=False)
    kind: Mapped[CategoryKind] = mapped_column(
        Enum(CategoryKind, native_enum=False, length=10),
        default=CategoryKind.EXPENSE,
        nullable=False,
    )
    color: Mapped[str] = mapped_column(String(9), default="#0B1F3A", nullable=False)
    icon: Mapped[str] = mapped_column(String(40), default="Wallet", nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User | None] = relationship(back_populates="categories")
    transactions: Mapped[list[Transaction]] = relationship(back_populates="category")
    budget_items: Mapped[list[BudgetItem]] = relationship(back_populates="category")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Category {self.name}>"
