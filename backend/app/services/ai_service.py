"""AI service: conversation persistence and insight phrasing."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.ai import assistant
from app.ai.provider import LLMError, get_provider
from app.ai.provider import status as provider_status
from app.ai.tools import TOOL_DESCRIPTIONS
from app.models import AIConversation, AIMessage, Insight, MessageRole, User

logger = logging.getLogger(__name__)

TITLE_MAX_LENGTH = 60
# Cap conversation length so a long thread cannot grow unbounded in one row set.
MAX_MESSAGES_RETURNED = 100


def status() -> dict:
    info = provider_status()
    info["available_tools"] = TOOL_DESCRIPTIONS
    return info


def list_conversations(session: Session, user: User) -> list[dict]:
    stmt = (
        select(
            AIConversation,
            func.count(AIMessage.id).label("message_count"),
        )
        .outerjoin(AIMessage, AIMessage.conversation_id == AIConversation.id)
        .where(AIConversation.user_id == user.id, AIConversation.is_archived.is_(False))
        .group_by(AIConversation.id)
        .order_by(AIConversation.updated_at.desc())
    )
    return [
        {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "message_count": int(count or 0),
        }
        for conversation, count in session.execute(stmt).all()
    ]


def get_conversation(session: Session, user: User, conversation_id: str) -> AIConversation | None:
    stmt = (
        select(AIConversation)
        .where(AIConversation.id == conversation_id, AIConversation.user_id == user.id)
        .options(joinedload(AIConversation.messages))
    )
    return session.scalars(stmt).unique().first()


def delete_conversation(session: Session, conversation: AIConversation) -> None:
    session.delete(conversation)
    session.flush()


def _title_from(question: str) -> str:
    title = " ".join(question.split())
    if len(title) > TITLE_MAX_LENGTH:
        title = title[: TITLE_MAX_LENGTH - 1].rstrip() + "…"
    return title or "New conversation"


def chat(
    session: Session,
    user: User,
    message: str,
    conversation_id: str | None = None,
    today: date | None = None,
) -> tuple[AIConversation, AIMessage, assistant.AssistantAnswer]:
    """Persist the exchange and return the assistant's reply."""
    conversation: AIConversation | None = None
    if conversation_id:
        conversation = get_conversation(session, user, conversation_id)
        if conversation is None:
            # Silently starting a fresh thread would hide a real bug (or an
            # attempt to read someone else's conversation).
            raise ValueError("Conversation not found")

    if conversation is None:
        conversation = AIConversation(user_id=user.id, title=_title_from(message))
        session.add(conversation)
        session.flush()

    session.add(AIMessage(conversation_id=conversation.id, role=MessageRole.USER, content=message))
    session.flush()

    answer = assistant.answer_question(session, user, message, today)

    assistant_message = AIMessage(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT,
        content=answer.content,
        tools_used=[
            {"name": tool.name, "arguments": tool.arguments, "summary": tool.summary}
            for tool in answer.tools
        ],
        retrieved_facts=answer.facts,
        generation_mode=answer.generation_mode,
    )
    session.add(assistant_message)

    # Touch the conversation so it sorts to the top of the list.
    conversation.updated_at = func.now()
    session.flush()
    session.refresh(assistant_message)

    return conversation, assistant_message, answer


def messages_for(session: Session, conversation: AIConversation) -> list[AIMessage]:
    stmt = (
        select(AIMessage)
        .where(AIMessage.conversation_id == conversation.id)
        .order_by(AIMessage.created_at)
        .limit(MAX_MESSAGES_RETURNED)
    )
    return list(session.scalars(stmt).all())


INSIGHT_SYSTEM_PROMPT = """You rewrite pre-computed personal-finance findings \
into one short, natural paragraph for the user.

You will be given a finding that the application already calculated: a title, a \
factual summary, why it matters, a suggested action, and the structured data \
behind it.

Rules:
1. Use ONLY the numbers present in the finding. Never add, adjust or recompute a \
figure, and never introduce a number of your own.
2. Write 2-3 sentences, in plain warm British English, addressed to the user.
3. Lead with what happened, then why it matters, then the action.
4. No headings, no bullet points, no emoji, no restating the title verbatim.
5. Do not give investment, tax or legal advice.
6. Amounts are Indian Rupees, formatted ₹1,234."""


def explain_insights(insights: list[Insight]) -> bool:
    """Add natural-language phrasing to insights. Returns whether AI was used.

    The insight is already complete and displayable without this: the deterministic
    ``summary`` / ``why_it_matters`` / ``suggested_action`` fields are always
    populated by the insight engine. This only adds an optional narrative layer.
    """
    provider = get_provider()
    if provider is None:
        return False

    used = False
    for insight in insights:
        if insight.ai_explanation:
            continue  # already phrased on a previous run

        payload = (
            f"Title: {insight.title}\n"
            f"Summary: {insight.summary}\n"
            f"Why it matters: {insight.why_it_matters}\n"
            f"Suggested action: {insight.suggested_action}\n"
            f"Structured data: {insight.data}"
        )
        try:
            insight.ai_explanation = provider.complete(INSIGHT_SYSTEM_PROMPT, payload)
            used = True
        except LLMError as exc:
            logger.warning("Could not generate AI explanation for insight: %s", exc)
            break  # provider is down; stop hammering it
        except Exception:
            logger.exception("Unexpected error generating AI insight explanation")
            break
    return used
