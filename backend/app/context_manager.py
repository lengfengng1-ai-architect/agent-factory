"""Context budget management for chat messages with file attachments."""

from typing import List, Dict, Any
from langchain.messages import SystemMessage, HumanMessage, AIMessage
from app import models
from app.file_utils import truncate_content, format_files_for_prompt

# Conservative token estimation: 1 token ~ 3.5 chars for CJK/English mix
TOKEN_ESTIMATE_RATIO = 3.5
# Reserve tokens for system prompt + user message + LLM response
RESERVE_TOKENS = 2000
# Budget allocation: files get 60%, history gets 40%
FILE_BUDGET_RATIO = 0.6
HISTORY_BUDGET_RATIO = 0.4
# Single file max chars before individual truncation
SINGLE_FILE_MAX_CHARS = 15000
# Files under this length are considered "short" and passed verbatim
SHORT_FILE_THRESHOLD = 8000

DEFAULT_CONTEXT_WINDOW = 128000


def estimate_tokens(text: str) -> int:
    """Estimate token count from character count."""
    if not text:
        return 0
    return max(1, int(len(text) / TOKEN_ESTIMATE_RATIO))


def get_model_context_window(db, agent: models.Agent) -> int:
    """Get the context window for an agent's model from provider_models."""
    if not agent.model:
        return DEFAULT_CONTEXT_WINDOW

    # Find provider first
    provider = db.query(models.Provider).filter(
        models.Provider.key == (agent.provider or "kimi").lower()
    ).first()

    if provider:
        model_record = (
            db.query(models.ProviderModel)
            .filter(
                models.ProviderModel.model_id == agent.model,
                models.ProviderModel.provider_id == provider.id,
            )
            .first()
        )
        if model_record and model_record.context_window:
            return model_record.context_window

    # Fallback: look up by model_id across all providers
    model_record = (
        db.query(models.ProviderModel)
        .filter(models.ProviderModel.model_id == agent.model)
        .first()
    )

    if model_record and model_record.context_window:
        return model_record.context_window

    return DEFAULT_CONTEXT_WINDOW


def _truncate_file_contents(
    file_contents: List[Dict[str, str]], file_budget_tokens: int
) -> List[Dict[str, str]]:
    """Apply truncation to file contents to fit within token budget.

    First applies per-file max limit, then if total still exceeds budget,
    redistributes budget equally across files.
    """
    if not file_contents:
        return []

    # Step 1: apply single-file max limit
    step1 = []
    for item in file_contents:
        content = item.get("content", "")
        name = item.get("name", "unknown")
        is_summary = item.get("is_summary", False)
        if len(content) > SINGLE_FILE_MAX_CHARS:
            content = truncate_content(content, SINGLE_FILE_MAX_CHARS, name)
        step1.append({"name": name, "content": content, "is_summary": is_summary})

    # Step 2: check total budget
    total_chars = sum(len(item["content"]) for item in step1)
    total_tokens = estimate_tokens("".join(item["content"] for item in step1))

    if total_tokens <= file_budget_tokens:
        return step1

    # Step 3: redistribute budget evenly
    per_file_tokens = max(500, file_budget_tokens // len(step1))
    per_file_chars = int(per_file_tokens * TOKEN_ESTIMATE_RATIO)

    result = []
    for item in step1:
        content = item["content"]
        if len(content) > per_file_chars:
            content = truncate_content(content, per_file_chars, item["name"])
        result.append({"name": item["name"], "content": content, "is_summary": item["is_summary"]})

    return result


def _truncate_history(
    history: List[Dict[str, Any]], history_budget_tokens: int
) -> List[Dict[str, Any]]:
    """Truncate chat history from oldest to newest to fit budget.

    Always keeps at least the last user-assistant pair if possible.
    """
    if not history:
        return []

    # Work backwards to find how many recent messages fit
    total_tokens = 0
    keep_count = 0

    for msg in reversed(history):
        content = msg.get("content", "")
        tokens = estimate_tokens(content)
        if total_tokens + tokens > history_budget_tokens and keep_count >= 2:
            break
        total_tokens += tokens
        keep_count += 1

    # If we couldn't even fit 1 message, keep at least the last one
    if keep_count == 0 and history:
        keep_count = 1

    start_idx = len(history) - keep_count
    return history[start_idx:]


def build_messages_with_budget(
    agent: models.Agent,
    history: List[Dict[str, Any]],
    user_message: str,
    file_contents: List[Dict[str, str]],
    context_window: int,
    system_prompt: str = None,
) -> List[SystemMessage | HumanMessage | AIMessage]:
    """Build the final message list for LLM invocation within context budget.

    Args:
        agent: The agent configuration.
        history: Full chat history (list of dicts with role/content).
        user_message: The current user message.
        file_contents: List of dicts with file name and content/summary.
        context_window: The model's max context window in tokens.
        system_prompt: Optional override for the system prompt. If not provided,
            uses agent.system_prompt.

    Returns:
        List of LangChain messages ready for LLM.
    """
    system_prompt = system_prompt or agent.system_prompt or "You are a helpful assistant."

    # 1. Calculate budgets
    total_budget = max(0, context_window - RESERVE_TOKENS)
    file_budget_tokens = int(total_budget * FILE_BUDGET_RATIO)
    history_budget_tokens = int(total_budget * HISTORY_BUDGET_RATIO)

    # 2. Truncate file contents
    truncated_files = _truncate_file_contents(file_contents, file_budget_tokens)

    # 3. Truncate history
    truncated_history = _truncate_history(history, history_budget_tokens)

    # 4. Build messages
    messages: List[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(content=system_prompt)
    ]

    for msg in truncated_history:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            # Preserve reasoning_content from Redis history if present
            kwargs = {}
            rc = msg.get("reasoning_content")
            if rc is not None:
                kwargs["additional_kwargs"] = {"reasoning_content": rc}
            messages.append(AIMessage(content=content, **kwargs))

    # 5. Build user message with file context
    if truncated_files:
        files_prompt = format_files_for_prompt(truncated_files)
        combined = f"{files_prompt}\n用户问题：{user_message}"
        messages.append(HumanMessage(content=combined))
    else:
        messages.append(HumanMessage(content=user_message))

    return messages


def should_summarize(content: str, file_mode: str = "auto") -> bool:
    """Determine if a file should be summarized based on content length and mode.

    Args:
        content: The extracted file content.
        file_mode: One of "truncate", "summary", "auto".

    Returns:
        True if summary mode should be used.
    """
    if file_mode == "summary":
        return len(content) > SHORT_FILE_THRESHOLD
    if file_mode == "truncate":
        return False
    # auto: summarize only long files
    return len(content) > SHORT_FILE_THRESHOLD
