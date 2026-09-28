"""AI assistant conversations and messages.

``AIMessage.retrieved_facts`` stores the exact structured data the backend
fetched before answering. That makes every assistant reply auditable: you can
open a message and see which financial tools ran and what they returned.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, uuid_pk
from app.models.enums import MessageRole

if TYPE_CHECKING:
    from app.models.user import User


class AIConversation(Base, TimestampMixin):
    __tablename__ = "ai_conversations"
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(160), default="New conversation", nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[AIMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AIMessage.created_at",
    )


class AIMessage(Base, TimestampMixin):
    __tablename__ = "ai_messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[str] = uuid_pk()
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("ai_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, native_enum=False, length=10), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Names of the data-retrieval tools that ran, and their verified results.
    tools_used: Mapped[list | None] = mapped_column(JSON, default=list, nullable=True)
    retrieved_facts: Mapped[dict | None] = mapped_column(JSON, default=dict, nullable=True)
    # "llm" when an external provider phrased the answer, "deterministic" when
    # the built-in template explainer did.
    generation_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    conversation: Mapped[AIConversation] = relationship(back_populates="messages")
