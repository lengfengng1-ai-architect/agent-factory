"""LLM-based file summarization with Redis caching."""

import hashlib
import asyncio
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app import models
from app.file_utils import (
    extract_text,
    compute_content_hash,
    format_summary_prompt,
)

SHORT_FILE_THRESHOLD = 8000  # Files under this length are passed verbatim
from app.redis_client import r

SUMMARY_CACHE_TTL = 86400  # 24 hours
SUMMARY_MAX_OUTPUT = 2000  # chars
SUMMARY_TIMEOUT = 30  # seconds


def _get_summary_cache_key(file_hash: str) -> str:
    return f"chat_file_summary:{file_hash}"


def get_cached_summary(file_hash: str) -> Optional[str]:
    """Get cached summary from Redis by content hash."""
    key = _get_summary_cache_key(file_hash)
    result = r.get(key)
    return result if result else None


def save_summary_cache(file_hash: str, summary: str):
    """Save summary to Redis with TTL."""
    key = _get_summary_cache_key(file_hash)
    r.set(key, summary, ex=SUMMARY_CACHE_TTL)


def _create_llm(agent: models.Agent, provider: models.Provider) -> ChatOpenAI:
    """Create a non-streaming LLM for summarization."""
    base_url = provider.base_url
    model = agent.model or ""
    api_key = agent.api_key or ""

    if provider.key == "custom":
        base_url = agent.api_url or base_url
    if provider.key == "ollama":
        api_key = api_key or "ollama"

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        streaming=False,
        max_tokens=1500,
    )


async def generate_summary(
    file_path: str,
    filename: str,
    agent: models.Agent,
    provider: models.Provider,
) -> str:
    """Generate a summary for a file using the agent's LLM.

    Returns the summary text, or an error message string if generation fails.
    """
    # Extract full content
    content = extract_text(file_path, filename)

    # Check if content is too short to summarize
    if len(content) <= SHORT_FILE_THRESHOLD:
        return content

    # Check cache first
    content_hash = compute_content_hash(content)
    cached = get_cached_summary(content_hash)
    if cached:
        return cached

    # Build summary prompt
    prompt = format_summary_prompt(content, filename)

    try:
        llm = _create_llm(agent, provider)

        messages = [
            SystemMessage(content="You are a helpful document summarizer."),
            HumanMessage(content=prompt),
        ]

        # Run with timeout
        response = await asyncio.wait_for(
            llm.ainvoke(messages),
            timeout=SUMMARY_TIMEOUT,
        )

        summary = response.content.strip()
        if not summary:
            summary = "[Error: Summary generation returned empty content]"

        # Cache the result
        save_summary_cache(content_hash, summary)
        return summary

    except asyncio.TimeoutError:
        return "[Error: Summary generation timed out after 30s]"
    except Exception as e:
        return f"[Error generating summary: {e}]"


def maybe_use_summary(
    file_path: str,
    filename: str,
    file_mode: str = "auto",
) -> dict:
    """Determine whether to use summary or full content for a file.

    Returns a dict with:
        - content: the text to use (either full or summary)
        - is_summary: bool
        - error: optional error message
    """
    content = extract_text(file_path, filename)

    # Check if this is an error/info message from extraction
    if content.startswith("[") and content.endswith("]"):
        return {"content": content, "is_summary": False, "error": None}

    # Determine mode
    use_summary = False
    if file_mode == "summary":
        use_summary = len(content) > SHORT_FILE_THRESHOLD
    elif file_mode == "auto":
        # Auto: code files → truncate, document files → summarize
        ext = filename.lower().split(".")[-1] if "." in filename else ""
        code_exts = {"py", "js", "jsx", "ts", "tsx", "java", "go", "rs", "c", "cpp", "h", "hpp",
                     "sql", "html", "css", "xml", "yaml", "yml", "json", "sh", "bash"}
        if ext in code_exts:
            use_summary = False  # Code files: always truncate
        else:
            use_summary = len(content) > SHORT_FILE_THRESHOLD

    if not use_summary:
        return {"content": content, "is_summary": False, "error": None}

    # Try to get cached summary
    content_hash = compute_content_hash(content)
    cached = get_cached_summary(content_hash)
    if cached:
        return {"content": cached, "is_summary": True, "error": None}

    # Summary needed but not cached - return full content for now
    # The caller should trigger async summary generation
    return {
        "content": content,
        "is_summary": False,
        "error": None,
        "needs_summary": True,
        "content_hash": content_hash,
    }
