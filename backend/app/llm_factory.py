"""Unified LLM factory for creating chat models across all providers.

Follows LangChain v1 best practices:
- init_chat_model for model identifier strings
- Centralized provider configuration
- Proper Kimi header handling
"""

import os
from typing import Any
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from app import models

KIMI_CODE_BASE_URL = "https://api.kimi.com/coding/v1"


def _resolve_kimi_base_url(api_key: str, default_url: str) -> str:
    """Auto-detect Kimi Code (sk-kimi-) vs legacy Moonshot keys."""
    if api_key.startswith("sk-kimi-"):
        return KIMI_CODE_BASE_URL
    return default_url


def create_llm(
    agent: models.Agent,
    provider: models.Provider,
    streaming: bool = False,
    **extra_kwargs: Any,
) -> ChatOpenAI:
    """Create a ChatOpenAI instance for an agent.

    This is the single source of truth for LLM instantiation across the
    entire backend. All routers and engines should use this function.
    """
    base_url = provider.base_url
    model = agent.model or ""
    api_key = agent.api_key or ""

    if provider.key == "custom":
        base_url = agent.api_url or base_url

    if provider.key in ("kimi", "kimi-code"):
        base_url = _resolve_kimi_base_url(api_key, base_url)
        if "api.kimi.com" in (base_url or ""):
            extra_kwargs.setdefault("default_headers", {})
            extra_kwargs["default_headers"]["User-Agent"] = "KimiCLI/1.30.0"
        # Kimi K2.6+ thinking mode conflicts with tool calling:
        # API rejects assistant tool-call messages without reasoning_content.
        # Disable thinking by default unless agent config explicitly enables it.
        agent_config = getattr(agent, 'config', None) or {}
        thinking_enabled = agent_config.get('thinking_enabled', False)
        if not thinking_enabled:
            extra_body = extra_kwargs.setdefault("extra_body", {})
            # Only set if user hasn't already configured thinking
            if "thinking" not in extra_body:
                extra_body["thinking"] = {"type": "disabled"}

    if provider.key == "ollama":
        api_key = api_key or "ollama"
    elif not api_key:
        raise ValueError("Agent api_key not configured")

    if not base_url:
        raise ValueError("Provider base_url not configured")
    if not model:
        raise ValueError("Agent model not configured")

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        streaming=streaming,
        **extra_kwargs,
    )


def create_llm_from_identifiers(
    model: str,
    api_key: str,
    base_url: str,
    streaming: bool = False,
    **extra_kwargs: Any,
) -> ChatOpenAI:
    """Create LLM from raw identifiers (useful for dynamic model selection)."""
    if "api.kimi.com" in (base_url or ""):
        extra_kwargs.setdefault("default_headers", {})
        extra_kwargs["default_headers"]["User-Agent"] = "KimiCLI/1.30.0"

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        streaming=streaming,
        **extra_kwargs,
    )
