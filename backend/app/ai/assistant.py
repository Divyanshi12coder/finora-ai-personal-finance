"""The AI financial assistant.

Request flow:

    question
      -> route_tools()          decide which data is needed
      -> run each tool          query the database via the service layer
      -> structured facts       verified numbers, with sources
      -> phrase_answer()        LLM rewrites the facts, or templates do
      -> answer

The model is given the retrieved facts and an instruction never to introduce a
number that is not in them. Because the facts are computed first, a provider
outage degrades phrasing quality only - never correctness.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.ai import tools as tool_module
from app.ai.provider import LLMError, get_provider
from app.models import User

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Finora's financial assistant, embedded in a personal \
finance application.

You have been given a block of VERIFIED FINANCIAL DATA that the application \
computed directly from this user's database records. Your job is to answer their \
question using only that data.

Absolute rules:
1. Never state a number that does not appear in the verified data. Do not \
estimate, extrapolate, round differently, or infer figures.
2. If the verified data does not contain what is needed to answer, say plainly \
that the information is not available and what the user could do about it \
(e.g. record more transactions, set a budget).
3. Never invent transactions, merchants, balances, dates or categories.
4. Amounts are in Indian Rupees; format them as ₹1,234 (no decimals unless the \
data has paise).
5. Be concise and specific: 2-4 short sentences, or a short list when comparing \
several categories. No preamble, no restating the question.
6. Where the data includes a caveat (forecast intervals, score disclaimers, \
low confidence), carry it through rather than presenting the figure as certain.
7. Never give regulated financial, investment, tax or legal advice. Describing \
what the user's own data shows is fine; recommending securities is not.

Write in plain, warm, direct British English."""


@dataclass
class AssistantAnswer:
    content: str
    tools: list[tool_module.ToolResult]
    facts: dict
    generation_mode: str  # "llm" | "deterministic"
    suggestions: list[str]


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------
# Ordered most-specific first; the first matching rule wins, and a couple of
# supporting tools are added for context.
_ROUTING_RULES: list[tuple[re.Pattern[str], list[str]]] = [
    (
        re.compile(r"\b(health|score|how am i doing|financial shape)\b", re.I),
        ["get_financial_health", "get_monthly_spending"],
    ),
    (
        re.compile(r"\b(forecast|predict|next month|projection|going to spend|expect)\b", re.I),
        ["get_forecast", "get_monthly_spending"],
    ),
    (
        re.compile(r"\b(budget|limit|allowance|over.?spend)\b", re.I),
        ["get_budget_status", "get_category_spending"],
    ),
    (
        re.compile(r"\b(goal|saving for|vacation fund|emergency fund|target)\b", re.I),
        ["get_goal_requirement", "get_goal_progress"],
    ),
    (
        re.compile(r"\b(unusual|suspicious|weird|strange|anomal|fraud|duplicate)\b", re.I),
        ["get_anomalies"],
    ),
    (
        re.compile(
            r"\b(if i (?:cut|reduce|lower|spend less)|how much (?:can|could) i save|reduce.*by)\b",
            re.I,
        ),
        ["get_savings_simulation", "get_category_spending"],
    ),
    (
        re.compile(
            r"\b(why|higher|lower|increase|decrease|compared|change[ds]?|difference|vs\.?|versus)\b",
            re.I,
        ),
        ["compare_periods", "get_monthly_spending"],
    ),
    (
        re.compile(r"\b(merchant|where did i|store|shop|brand|most at)\b", re.I),
        ["get_top_merchants", "get_category_spending"],
    ),
    (
        re.compile(r"\b(recent|last few|latest|show me my transactions)\b", re.I),
        ["get_recent_transactions"],
    ),
    (
        re.compile(r"\b(insight|advice|tips|what should i|recommend)\b", re.I),
        ["get_insights", "get_monthly_spending"],
    ),
    (
        re.compile(r"\b(most|top|biggest|largest|highest)\b", re.I),
        ["get_category_spending", "get_top_merchants"],
    ),
    (
        re.compile(r"\b(spend|spent|spending|expense|cost|paid)\b", re.I),
        ["get_category_spending", "get_monthly_spending"],
    ),
    (
        re.compile(r"\b(income|earn|earned|salary|savings? rate|saved)\b", re.I),
        ["get_monthly_spending"],
    ),
]

_DEFAULT_TOOLS = ["get_monthly_spending", "get_category_spending"]


def _extract_reduction_pct(question: str) -> float:
    match = re.search(r"(\d{1,2})\s*%", question)
    if match:
        return float(match.group(1))
    if re.search(r"\bhalf\b", question, re.I):
        return 50.0
    return 20.0


def route_tools(question: str) -> list[str]:
    """Select which tools to run for a question."""
    selected: list[str] = []
    for pattern, tool_names in _ROUTING_RULES:
        if pattern.search(question):
            for name in tool_names:
                if name not in selected:
                    selected.append(name)
            # Two matched rules give enough context; more just adds noise.
            if len(selected) >= 3:
                break

    if not selected:
        selected = list(_DEFAULT_TOOLS)
    return selected[:4]


def run_tools(
    session: Session, user: User, question: str, today: date | None = None
) -> list[tool_module.ToolResult]:
    """Execute the routed tools and collect their structured results."""
    today = today or date.today()
    period, label = tool_module.parse_period(question, today)
    category = tool_module.extract_category(session, user, question)

    results: list[tool_module.ToolResult] = []
    for name in route_tools(question):
        function = tool_module.TOOL_REGISTRY.get(name)
        if function is None:  # pragma: no cover - registry is static
            continue
        try:
            results.append(
                function(
                    session=session,
                    user=user,
                    period=period,
                    label=label,
                    category=category,
                    question=question,
                    reduction_pct=_extract_reduction_pct(question),
                )
            )
        except Exception:
            # A failing tool must not fail the whole answer.
            logger.exception("Assistant tool %s failed", name)
    return results


# --------------------------------------------------------------------------
# Answer generation
# --------------------------------------------------------------------------
def _facts_payload(results: list[tool_module.ToolResult]) -> dict:
    return {result.name: result.data for result in results}


def phrase_with_llm(question: str, results: list[tool_module.ToolResult]) -> str | None:
    """Ask the provider to phrase the verified facts. ``None`` on failure."""
    provider = get_provider()
    if provider is None:
        return None

    facts = json.dumps(_facts_payload(results), indent=2, default=str)
    prompt = (
        f"User's question:\n{question}\n\n"
        f"VERIFIED FINANCIAL DATA (the only numbers you may use):\n{facts}\n\n"
        "Answer the question using only these figures. If they do not contain "
        "what is needed, say so."
    )

    try:
        return provider.complete(SYSTEM_PROMPT, prompt)
    except LLMError as exc:
        logger.warning("AI provider unavailable, using deterministic answer: %s", exc)
        return None
    except Exception:
        logger.exception("Unexpected AI provider error; using deterministic answer")
        return None


def phrase_deterministically(question: str, results: list[tool_module.ToolResult]) -> str:
    """Build the answer from the tools' own summaries.

    Every tool returns a human-readable ``summary`` of what it found, so this
    fallback contains the same verified numbers as the LLM path - the prose is
    simply plainer. This is why the assistant remains useful with no API key.
    """
    if not results:
        return (
            "I couldn't find any financial data to answer that. Add a few "
            "transactions (or load the demo data) and ask me again."
        )

    unavailable = [r for r in results if not r.data.get("available", True)]
    available = [r for r in results if r.data.get("available", True)]

    if not available:
        reasons = []
        for result in unavailable:
            reason = result.data.get("reason")
            if reason and reason not in reasons:
                reasons.append(reason)
        return " ".join(reasons) or ("I don't have enough data recorded to answer that yet.")

    lines = [result.summary for result in available if result.summary]
    # Deduplicate while preserving order - two tools can surface the same fact.
    seen: set[str] = set()
    unique = [line for line in lines if not (line in seen or seen.add(line))]

    answer = (
        " ".join(unique[:2])
        if len(unique) <= 2
        else unique[0] + "\n\n" + "\n".join(f"• {line}" for line in unique[1:4])
    )

    if unavailable:
        missing = unavailable[0].data.get("reason")
        if missing:
            answer += f"\n\nOne thing I couldn't check: {missing}"

    return answer


_SUGGESTION_POOL = [
    "Where did I spend the most this month?",
    "Why are my expenses higher than last month?",
    "How much did I spend on food this month?",
    "How am I doing against my budget?",
    "How much can I save if I cut shopping by 20%?",
    "What's my financial health score?",
    "What does my cash flow look like next month?",
    "Are there any unusual transactions?",
    "How much do I need to save monthly for my goals?",
    "Which subscriptions am I paying for?",
]


def _suggestions(asked: str) -> list[str]:
    lowered = asked.lower().strip()
    return [s for s in _SUGGESTION_POOL if s.lower() != lowered][:4]


def answer_question(
    session: Session, user: User, question: str, today: date | None = None
) -> AssistantAnswer:
    """Full pipeline: retrieve verified facts, then phrase them."""
    results = run_tools(session, user, question, today)

    content = phrase_with_llm(question, results)
    mode = "llm"
    if content is None:
        content = phrase_deterministically(question, results)
        mode = "deterministic"

    logger.info(
        "Assistant answered for user %s using %s (mode=%s)",
        user.id,
        [r.name for r in results],
        mode,
    )

    return AssistantAnswer(
        content=content,
        tools=results,
        facts=_facts_payload(results),
        generation_mode=mode,
        suggestions=_suggestions(question),
    )


def suggested_questions() -> list[str]:
    return list(_SUGGESTION_POOL)
