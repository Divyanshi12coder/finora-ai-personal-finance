"""LLM provider abstraction.

Two things matter here:

1. **Swappability** - the provider is chosen by an environment variable, and
   adding one means implementing ``LLMProvider``. No caller knows which vendor
   is in use.

2. **Optionality** - when no API key is configured, ``get_provider`` returns
   ``None`` and the assistant falls back to a deterministic template explainer.
   The product does not break; it explains. Since the *numbers* always come from
   the backend, the fallback answers contain exactly the same facts - only the
   prose is less fluent.

The provider is only ever asked to phrase facts that the backend already
computed. It is never given raw database access and never asked to do arithmetic.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Provider call failed. Callers fall back to deterministic phrasing."""


class LLMProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str) -> str: ...


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    DEFAULT_BASE_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        url = settings.AI_BASE_URL or self.DEFAULT_BASE_URL
        try:
            response = httpx.post(
                url,
                timeout=settings.AI_TIMEOUT_SECONDS,
                headers={
                    "x-api-key": settings.AI_API_KEY,
                    "anthropic-version": self.API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": settings.AI_MODEL,
                    "max_tokens": settings.AI_MAX_TOKENS,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            # Never log the key or the full request body.
            raise LLMError(f"AI provider returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"AI provider request failed: {type(exc).__name__}") from exc
        except ValueError as exc:
            raise LLMError("AI provider returned a malformed response") from exc

        blocks = payload.get("content") or []
        text = "".join(
            block.get("text", "") for block in blocks if block.get("type") == "text"
        ).strip()
        if not text:
            raise LLMError("AI provider returned an empty response")
        return text


class OpenAICompatibleProvider(LLMProvider):
    """Works with OpenAI and any API that mirrors its chat-completions shape."""

    name = "openai"
    DEFAULT_BASE_URL = "https://api.openai.com/v1/chat/completions"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        url = settings.AI_BASE_URL or self.DEFAULT_BASE_URL
        try:
            response = httpx.post(
                url,
                timeout=settings.AI_TIMEOUT_SECONDS,
                headers={
                    "Authorization": f"Bearer {settings.AI_API_KEY}",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.AI_MODEL,
                    "max_tokens": settings.AI_MAX_TOKENS,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise LLMError(f"AI provider returned {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"AI provider request failed: {type(exc).__name__}") from exc
        except ValueError as exc:
            raise LLMError("AI provider returned a malformed response") from exc

        try:
            text = payload["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError) as exc:
            raise LLMError("AI provider returned an unexpected response shape") from exc
        if not text:
            raise LLMError("AI provider returned an empty response")
        return text


_PROVIDERS: dict[str, type[LLMProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAICompatibleProvider,
    # Any OpenAI-compatible gateway works by pointing AI_BASE_URL at it.
    "openai-compatible": OpenAICompatibleProvider,
}


def get_provider() -> LLMProvider | None:
    """Return the configured provider, or ``None`` when AI is not configured."""
    if not settings.ai_configured:
        return None

    provider_class = _PROVIDERS.get(settings.AI_PROVIDER.lower())
    if provider_class is None:
        logger.warning(
            "Unknown AI_PROVIDER %r; supported: %s. Falling back to " "deterministic explanations.",
            settings.AI_PROVIDER,
            ", ".join(sorted(_PROVIDERS)),
        )
        return None
    return provider_class()


def status() -> dict:
    configured = settings.ai_configured
    provider = settings.AI_PROVIDER
    known = provider.lower() in _PROVIDERS

    if configured and known:
        message = (
            f"Connected to {provider} ({settings.AI_MODEL}). The assistant retrieves "
            "your financial data from the backend first, then uses the model only to "
            "explain those verified figures."
        )
        mode = "llm"
    elif configured and not known:
        message = (
            f"AI_PROVIDER '{provider}' is not recognised. Supported values: "
            f"{', '.join(sorted(_PROVIDERS))}. Using built-in explanations."
        )
        mode = "deterministic"
    else:
        message = (
            "No AI API key is configured, so the assistant answers using Finora's "
            "built-in explanation engine. Answers still come from your real "
            "financial data - set AI_API_KEY in your environment for more "
            "conversational phrasing."
        )
        mode = "deterministic"

    return {
        "configured": configured and known,
        "provider": provider,
        "model": settings.AI_MODEL if configured else None,
        "mode": mode,
        "message": message,
    }
