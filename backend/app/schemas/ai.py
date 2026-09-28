"""AI assistant schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import MessageRole
from app.schemas.common import ORMModel


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


class ToolCallOut(BaseModel):
    name: str
    arguments: dict
    summary: str = Field(description="One-line description of what was retrieved")


class AIMessageOut(ORMModel):
    id: str
    role: MessageRole
    content: str
    tools_used: list | None
    retrieved_facts: dict | None
    generation_mode: str | None
    created_at: datetime


class ChatResponse(BaseModel):
    conversation_id: str
    message: AIMessageOut
    tools_used: list[ToolCallOut]
    # "llm" when an external provider phrased the reply, "deterministic" when the
    # built-in explainer did. Surfaced in the UI so the user always knows.
    generation_mode: str
    ai_configured: bool
    suggestions: list[str] = Field(default_factory=list)


class ConversationOut(ORMModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ConversationDetail(ORMModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[AIMessageOut]


class AIStatusResponse(BaseModel):
    configured: bool
    provider: str
    model: str | None
    mode: str
    message: str
    available_tools: list[dict]
