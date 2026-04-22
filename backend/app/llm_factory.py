"""Unified LLM factory for creating chat models across all providers.

Follows LangChain v1 best practices:
- Provider-specific ChatModel classes for full feature support (reasoning, etc.)
- Centralized provider configuration
- Proper Kimi header handling
"""

import os
from typing import Any
from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk
from app import models

KIMI_CODE_BASE_URL = "https://api.kimi.com/coding/v1"


class ChatKimi(ChatOpenAI):
    """Kimi chat model with reasoning_content support.

    Kimi K2.6+ returns thinking/reasoning content via the `reasoning_content`
    delta field when thinking is enabled. The base ChatOpenAI discards this
    non-standard field; this subclass preserves it in additional_kwargs.
    """

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if (choices := chunk.get("choices")) and generation_chunk:
            top = choices[0]
            if isinstance(generation_chunk.message, AIMessageChunk):
                generation_chunk.message.response_metadata = {
                    **generation_chunk.message.response_metadata,
                    "model_provider": "kimi",
                }
                # Kimi returns reasoning_content in delta when thinking is enabled
                if (
                    reasoning_content := top.get("delta", {}).get("reasoning_content")
                ) is not None:
                    generation_chunk.message.additional_kwargs["reasoning_content"] = (
                        reasoning_content
                    )
        return generation_chunk


class ChatAlibaba(ChatOpenAI):
    """Alibaba (Qwen) chat model with reasoning_content support."""

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if (choices := chunk.get("choices")) and generation_chunk:
            top = choices[0]
            if isinstance(generation_chunk.message, AIMessageChunk):
                generation_chunk.message.response_metadata = {
                    **generation_chunk.message.response_metadata,
                    "model_provider": "alibaba",
                }
                # Qwen reasoning models may return reasoning_content
                if (
                    reasoning_content := top.get("delta", {}).get("reasoning_content")
                ) is not None:
                    generation_chunk.message.additional_kwargs["reasoning_content"] = (
                        reasoning_content
                    )
                # Some Qwen versions use "reasoning" field
                elif (reasoning := top.get("delta", {}).get("reasoning")) is not None:
                    generation_chunk.message.additional_kwargs["reasoning_content"] = (
                        reasoning
                    )
        return generation_chunk


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
    """Create a ChatModel instance for an agent.

    This is the single source of truth for LLM instantiation across the
    entire backend. All routers and engines should use this function.

    Provider-specific classes are used to ensure full feature support:
    - DeepSeek -> ChatDeepSeek (reasoning_content support)
    - Kimi -> ChatKimi (reasoning_content support)
    - Alibaba/Qwen -> ChatAlibaba (reasoning_content support)
    - Others -> ChatOpenAI (standard OpenAI-compatible)
    """
    base_url = provider.base_url
    model = agent.model or ""
    api_key = agent.api_key or ""

    if provider.key == "custom":
        base_url = agent.api_url or base_url

    # Kimi base URL resolution
    if provider.key in ("kimi", "kimi-code"):
        base_url = _resolve_kimi_base_url(api_key, base_url)
        if "api.kimi.com" in (base_url or ""):
            extra_kwargs.setdefault("default_headers", {})
            extra_kwargs["default_headers"]["User-Agent"] = "KimiCLI/1.30.0"

    # Thinking mode configuration
    agent_config = getattr(agent, "config", None) or {}
    thinking_enabled = agent_config.get("thinking_enabled", False)

    if provider.key in ("kimi", "kimi-code"):
        if thinking_enabled:
            # Enable Kimi thinking mode
            extra_body = extra_kwargs.setdefault("extra_body", {})
            if "thinking" not in extra_body:
                extra_body["thinking"] = {"type": "enabled"}
        else:
            # Disable thinking by default to prevent 400 errors during tool calls
            extra_body = extra_kwargs.setdefault("extra_body", {})
            if "thinking" not in extra_body:
                extra_body["thinking"] = {"type": "disabled"}

    if provider.key == "deepseek":
        if thinking_enabled:
            # DeepSeek reasoning model
            extra_body = extra_kwargs.setdefault("extra_body", {})
            if "model" not in extra_kwargs:
                # Use deepseek-reasoner when thinking is enabled
                model = "deepseek-reasoner"

    if provider.key == "ollama":
        api_key = api_key or "ollama"
    elif not api_key:
        raise ValueError("Agent api_key not configured")

    if not base_url:
        raise ValueError("Provider base_url not configured")
    if not model:
        raise ValueError("Agent model not configured")

    # Provider-specific model class selection
    if provider.key == "deepseek":
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(
            model=model,
            api_key=api_key,
            base_url=base_url,
            streaming=streaming,
            **extra_kwargs,
        )
    elif provider.key in ("kimi", "kimi-code"):
        return ChatKimi(
            model=model,
            api_key=api_key,
            base_url=base_url,
            streaming=streaming,
            **extra_kwargs,
        )
    elif provider.key == "alibaba":
        return ChatAlibaba(
            model=model,
            api_key=api_key,
            base_url=base_url,
            streaming=streaming,
            **extra_kwargs,
        )
    else:
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
