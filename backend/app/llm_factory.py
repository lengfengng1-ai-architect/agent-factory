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
from langchain_core.messages import AIMessageChunk, AIMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_core.language_models import LanguageModelInput
from app import models
from app.logger import get_logger, truncate_for_log

logger = get_logger(__name__)

KIMI_CODE_BASE_URL = "https://api.kimi.com/coding/v1"


class ChatKimi(ChatOpenAI):
    """Kimi chat model with reasoning_content support.

    Kimi K2.6+ returns thinking/reasoning content via the `reasoning_content`
    delta field when thinking is enabled. The base ChatOpenAI discards this
    non-standard field; this subclass preserves it in additional_kwargs.

    Also injects reasoning_content into outgoing assistant messages to prevent
    400 errors during multi-turn tool calling (Kimi requires this field on
    all assistant messages when thinking mode is active).
    """

    def _get_request_payload(
        self,
        input_: LanguageModelInput,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        """Build request payload and ensure reasoning_content on assistant msgs."""
        # Extract reasoning_content from AIMessage.additional_kwargs before
        # LangChain's _convert_message_to_dict drops it.
        raw_messages = self._convert_input(input_).to_messages()
        reasoning_contents: list[str | None] = []
        for m in raw_messages:
            if isinstance(m, AIMessage):
                reasoning_contents.append(m.additional_kwargs.get("reasoning_content"))
            else:
                reasoning_contents.append(None)

        payload = super()._get_request_payload(input_, stop=stop, **kwargs)

        # Kimi API requires reasoning_content on ALL assistant messages when
        # thinking is enabled (which is the default for kimi-k2.5/k2.6).
        # Inject preserved reasoning_content or empty string to satisfy validation.
        if "messages" in payload and len(payload["messages"]) == len(reasoning_contents):
            for msg, rc in zip(payload["messages"], reasoning_contents):
                if msg.get("role") == "assistant" and rc is not None:
                    msg["reasoning_content"] = rc
                elif msg.get("role") == "assistant" and "reasoning_content" not in msg:
                    msg["reasoning_content"] = ""

        # Log request payload for debugging
        model_name = payload.get("model", self.model_name)
        msg_count = len(payload.get("messages", []))
        extra_body = payload.get("extra_body", {})
        logger.info(
            f"[LLM REQUEST] model={model_name} messages={msg_count} "
            f"extra_body={truncate_for_log(extra_body, 500)} "
            f"stream={payload.get('stream')} "
            f"tools={len(payload.get('tools', []))}"
        )
        for i, msg in enumerate(payload.get("messages", [])):
            role = msg.get("role", "unknown")
            content_preview = truncate_for_log(msg.get("content", ""), 300)
            tool_calls = msg.get("tool_calls", [])
            rc = msg.get("reasoning_content", "")
            rc_info = f" rc={truncate_for_log(rc, 100)}" if rc else ""
            tc_info = f" tool_calls={len(tool_calls)}" if tool_calls else ""
            logger.debug(f"  msg[{i}] {role}: {content_preview}{rc_info}{tc_info}")

        return payload

    def _create_chat_result(
        self,
        response: dict | Any,
        generation_info: dict | None = None,
    ) -> ChatResult:
        """Override to preserve reasoning_content in non-streaming responses."""
        result = super()._create_chat_result(response, generation_info)

        # Extract reasoning_content from response dict for non-streaming path
        response_dict = response if isinstance(response, dict) else (
            response.model_dump(
                exclude={"choices": {"__all__": {"message": {"parsed"}}}}
            ) if hasattr(response, "model_dump") else {}
        )

        choices = response_dict.get("choices") or []
        for idx, gen in enumerate(result.generations):
            if isinstance(gen.message, AIMessage) and idx < len(choices):
                msg_dict = choices[idx].get("message", {})
                if (rc := msg_dict.get("reasoning_content")) is not None:
                    gen.message.additional_kwargs["reasoning_content"] = rc
                # Also check top-level reasoning field used by some providers
                elif (rc := msg_dict.get("reasoning")) is not None:
                    gen.message.additional_kwargs["reasoning_content"] = rc

        # Log response for debugging
        for idx, gen in enumerate(result.generations):
            msg = gen.message
            if isinstance(msg, AIMessage):
                rc = msg.additional_kwargs.get("reasoning_content", "")
                tc = msg.tool_calls
                logger.info(
                    f"[LLM RESPONSE] content={truncate_for_log(msg.content, 300)} "
                    f"reasoning={truncate_for_log(rc, 200) if rc else 'N/A'} "
                    f"tool_calls={len(tc) if tc else 0} "
                    f"finish_reason={gen.generation_info.get('finish_reason') if gen.generation_info else 'N/A'}"
                )

        return result

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
                    logger.debug(f"[LLM STREAM CHUNK] reasoning={truncate_for_log(reasoning_content, 200)}")
                delta_content = top.get("delta", {}).get("content", "")
                if delta_content:
                    logger.debug(f"[LLM STREAM CHUNK] content={truncate_for_log(delta_content, 200)}")
                delta_tc = top.get("delta", {}).get("tool_calls", [])
                if delta_tc:
                    logger.debug(f"[LLM STREAM CHUNK] tool_calls_delta={truncate_for_log(delta_tc, 300)}")
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

    logger.info(
        f"[CREATE LLM] provider={provider.key} model={model} "
        f"base_url={base_url} streaming={streaming} "
        f"extra_kwargs_keys={list(extra_kwargs.keys())}"
    )

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
