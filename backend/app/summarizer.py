"""LLM-based file summarization with Redis caching."""

import hashlib
import asyncio
import os
from pathlib import Path
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app import models
from app.database import SessionLocal
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


def get_summary_from_db(content_hash: str) -> models.FileSummary | None:
    """Get cached summary from SQLite by content hash."""
    db = SessionLocal()
    try:
        return db.query(models.FileSummary).filter(models.FileSummary.content_hash == content_hash).first()
    finally:
        db.close()


def save_summary_to_db(
    content_hash: str,
    file_name: str,
    file_ext: str,
    file_size: int,
    char_count: int,
    summary: str,
    agent_id: int,
    model_id: str,
    group_id: int | None = None,
):
    """Save summary to SQLite. Update if content_hash exists, else insert."""
    db = SessionLocal()
    try:
        existing = db.query(models.FileSummary).filter(models.FileSummary.content_hash == content_hash).first()
        if existing:
            existing.summary = summary
            existing.summary_char_count = len(summary)
        else:
            new_summary = models.FileSummary(
                content_hash=content_hash,
                file_name=file_name,
                file_ext=file_ext,
                file_size=file_size,
                char_count=char_count,
                summary=summary,
                summary_char_count=len(summary),
                agent_id=agent_id,
                group_id=group_id,
                model_id=model_id,
            )
            db.add(new_summary)
        db.commit()
    finally:
        db.close()


def get_summaries_for_agent(agent_id: int) -> list[dict]:
    """Query all historical summaries for a given agent."""
    db = SessionLocal()
    try:
        summaries = (
            db.query(models.FileSummary)
            .filter(models.FileSummary.agent_id == agent_id)
            .order_by(models.FileSummary.created_at.desc())
            .all()
        )
        return [
            {
                "id": s.id,
                "file_name": s.file_name,
                "summary": s.summary[:200] if s.summary else "",
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in summaries
        ]
    finally:
        db.close()


def get_summaries_for_group(group_id: int) -> list[dict]:
    """Query all historical summaries for a given group."""
    db = SessionLocal()
    try:
        summaries = (
            db.query(models.FileSummary)
            .filter(models.FileSummary.group_id == group_id)
            .order_by(models.FileSummary.created_at.desc())
            .all()
        )
        return [
            {
                "id": s.id,
                "file_name": s.file_name,
                "summary": s.summary[:200] if s.summary else "",
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in summaries
        ]
    finally:
        db.close()


def _create_llm(agent: models.Agent, provider: models.Provider) -> ChatOpenAI:
    """Create a non-streaming LLM for summarization."""
    base_url = provider.base_url
    model = agent.model or ""
    api_key = agent.api_key or ""

    if provider.key == "custom":
        base_url = agent.api_url or base_url
    if provider.key == "kimi":
        from app.task_engine import _resolve_kimi_base_url
        base_url = _resolve_kimi_base_url(api_key, base_url)
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

    # Truncate content for summary generation to fit within LLM context window
    # Most models support 128k context; we keep content under ~30k chars
    # to leave room for the prompt template + system message + output
    MAX_CHARS_FOR_SUMMARY = 30000
    summary_content = content
    if len(content) > MAX_CHARS_FOR_SUMMARY:
        from app.file_utils import truncate_content
        summary_content = truncate_content(content, MAX_CHARS_FOR_SUMMARY, filename)

    # Build summary prompt
    prompt = format_summary_prompt(summary_content, filename)

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

        # Persist successful summaries to SQLite
        if not summary.startswith("[Error"):
            save_summary_to_db(
                content_hash=content_hash,
                file_name=filename,
                file_ext=Path(filename).suffix.lstrip("."),
                file_size=os.path.getsize(file_path),
                char_count=len(content),
                summary=summary,
                agent_id=agent.id,
                model_id=agent.model,
            )

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

    # Check SQLite DB if Redis miss
    db_summary = get_summary_from_db(content_hash)
    if db_summary:
        # Backfill Redis cache
        save_summary_cache(content_hash, db_summary.summary)
        return {
            "content": db_summary.summary,
            "is_summary": True,
            "error": None,
            "db_id": db_summary.id,
        }

    # Summary needed but not cached - return full content for now
    # The caller should trigger async summary generation
    return {
        "content": content,
        "is_summary": False,
        "error": None,
        "needs_summary": True,
        "content_hash": content_hash,
    }
