"""AI assistant endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, not_found
from app.models import User
from app.schemas.ai import (
    AIMessageOut,
    AIStatusResponse,
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationOut,
    ToolCallOut,
)
from app.schemas.common import Message
from app.services import ai_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI Assistant"])


@router.get(
    "/status",
    response_model=AIStatusResponse,
    summary="Assistant configuration and available data tools",
    description=(
        "Reports whether an external LLM provider is configured and lists the "
        "data-retrieval tools the assistant can call. When no provider is "
        "configured the assistant still answers from your real data using the "
        "built-in explanation engine."
    ),
)
def status() -> AIStatusResponse:
    return AIStatusResponse.model_validate(ai_service.status())


@router.get(
    "/suggestions",
    response_model=list[str],
    summary="Example questions",
)
def suggestions() -> list[str]:
    from app.ai.assistant import suggested_questions

    return suggested_questions()


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask the assistant a question",
    description=(
        "The backend first decides which financial data the question needs, runs "
        "those retrieval tools against the database, and only then asks the "
        "language model to phrase the verified results. The response includes "
        "which tools ran and what they returned, so every answer is auditable. "
        "The model is instructed never to introduce a number that is not in the "
        "retrieved facts, and if no provider is configured the same facts are "
        "phrased by the built-in engine."
    ),
)
def chat(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ChatResponse:
    try:
        conversation, message, answer = ai_service.chat(
            session, user, payload.message, payload.conversation_id
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise not_found("Conversation") from exc

    session.refresh(message)
    provider = ai_service.status()

    return ChatResponse(
        conversation_id=conversation.id,
        message=AIMessageOut.model_validate(message),
        tools_used=[
            ToolCallOut(name=t.name, arguments=t.arguments, summary=t.summary) for t in answer.tools
        ],
        generation_mode=answer.generation_mode,
        ai_configured=provider["configured"],
        suggestions=answer.suggestions,
    )


@router.get(
    "/conversations",
    response_model=list[ConversationOut],
    summary="List conversations",
)
def list_conversations(
    user: User = Depends(get_current_user), session: Session = Depends(get_db)
) -> list[ConversationOut]:
    return [
        ConversationOut.model_validate(row) for row in ai_service.list_conversations(session, user)
    ]


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
    summary="Get a conversation with its messages",
)
def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> ConversationDetail:
    conversation = ai_service.get_conversation(session, user, conversation_id)
    if conversation is None:
        raise not_found("Conversation")

    messages = ai_service.messages_for(session, conversation)
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[AIMessageOut.model_validate(m) for m in messages],
    )


@router.delete(
    "/conversations/{conversation_id}",
    response_model=Message,
    summary="Delete a conversation",
)
def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> Message:
    conversation = ai_service.get_conversation(session, user, conversation_id)
    if conversation is None:
        raise not_found("Conversation")

    ai_service.delete_conversation(session, conversation)
    session.commit()
    return Message(detail="Conversation deleted")
