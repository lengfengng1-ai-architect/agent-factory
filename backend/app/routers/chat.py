import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.redis_client import (
    get_chat_history, append_chat_message, append_group_chat_message,
    get_chat_files,
)
from app.file_utils import extract_text
from app.context_manager import build_messages_with_budget, get_model_context_window
from app.summarizer import generate_summary, maybe_use_summary, get_summaries_for_agent
from app.tools import get_agent_tools, _has_browser_tools, _BROWSER_TOOL_GUIDE
from app.llm_factory import create_llm
from app.common import get_agent_provider
from app.logger import get_logger, truncate_for_log
from langchain.agents import create_agent
from langchain.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from pydantic import BaseModel, Field
import json
import os

logger = get_logger(__name__)

router = APIRouter()


@router.get("/{agent_id}/chat/history")
def get_agent_chat_history(agent_id: int):
    return {"messages": get_chat_history(agent_id)}


class ChatPayload(BaseModel):
    message: str = Field(..., description="User message text")
    files: list[str] = Field(default_factory=list, description="List of file IDs to attach")
    file_mode: str = Field(default="auto", description="File processing mode: auto, truncate, summary")
    group_id: int | None = Field(default=None, description="Optional group ID for group chat history")


@router.post("/{agent_id}/chat")
async def chat_with_agent(agent_id: int, payload: ChatPayload, db: Session = Depends(get_db)):
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    user_message = payload.message
    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")

    # Validate provider and build LLM
    try:
        provider = get_agent_provider(db, agent)
        llm = create_llm(agent, provider, streaming=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    system_prompt = agent.system_prompt or "You are a helpful assistant."

    # Save user message
    append_chat_message(agent_id, "user", user_message)
    group_id = payload.group_id
    if group_id:
        append_group_chat_message(group_id, "user", 0, "User", user_message)

    # Build messages with history and file attachments
    history = get_chat_history(agent_id)
    file_ids = payload.files or []
    file_mode = payload.file_mode or "auto"
    file_contents = []

    if file_ids:
        uploaded_files = get_chat_files(agent_id)
        file_id_to_meta = {f.get("id"): f for f in uploaded_files}

        for fid in file_ids:
            meta = file_id_to_meta.get(fid)
            if not meta:
                continue
            path = meta.get("path", "")
            name = meta.get("name", "unknown")
            if not path or not os.path.exists(path):
                continue

            result = maybe_use_summary(path, name, file_mode)
            content = result.get("content", "")
            is_summary = result.get("is_summary", False)

            if result.get("needs_summary"):
                try:
                    summary = await asyncio.wait_for(
                        generate_summary(path, name, agent, provider),
                        timeout=15,
                    )
                    if not summary.startswith("[Error"):
                        content = summary
                        is_summary = True
                except asyncio.TimeoutError:
                    pass

            file_contents.append({"name": name, "content": content, "is_summary": is_summary})

    # Load historical summaries for this agent (up to 5 most recent)
    historical_summaries = get_summaries_for_agent(agent_id)
    if historical_summaries:
        for hs in historical_summaries[:5]:
            file_contents.append({
                "name": hs["file_name"] + "（历史摘要）",
                "content": hs["summary"],
                "is_summary": True,
            })

    # Determine file root directory
    override_root = None
    if group_id:
        group = db.query(models.Group).filter(models.Group.id == group_id).first()
        if group and group.file_root_dir:
            override_root = group.file_root_dir

    tools = get_agent_tools(agent, override_root_dir=override_root)
    if _has_browser_tools(tools):
        system_prompt += _BROWSER_TOOL_GUIDE

    context_window = get_model_context_window(db, agent)
    messages = build_messages_with_budget(
        agent=agent,
        history=history,
        user_message=user_message,
        file_contents=file_contents,
        context_window=context_window,
        system_prompt=system_prompt,
    )

    async def stream_response():
        """Stream agent response directly using agent.astream().

        Supports:
        - Token-level streaming for fast first-token display
        - Reasoning/thinking content from providers (DeepSeek, Kimi, etc.)
        - Tool call notifications
        """
        full_response = ""
        reasoning_buffer = ""

        def _extract_message(event):
            """Extract AIMessage from v1 tuple or v2 dict format."""
            if isinstance(event, tuple) and len(event) > 0:
                return event[0]
            if isinstance(event, dict):
                data = event.get("data")
                if isinstance(data, tuple) and len(data) > 0:
                    return data[0]
            return event

        def _extract_reasoning(msg) -> str:
            """Extract incremental reasoning content from message chunk.

            Provider-specific extraction order:
            1. additional_kwargs['reasoning_content'] — DeepSeek (ChatDeepSeek), Kimi (ChatKimi)
            2. reasoning_content attribute — future native support
            3. content_blocks — OpenAI o1-style reasoning blocks
            """
            # DeepSeek / Kimi store reasoning in additional_kwargs as incremental tokens
            reasoning = msg.additional_kwargs.get('reasoning_content', '')
            if reasoning:
                return reasoning
            # Native attribute (for future provider subclasses)
            reasoning = getattr(msg, 'reasoning_content', None)
            if reasoning:
                return reasoning
            # OpenAI o1-style content blocks
            blocks = getattr(msg, 'content_blocks', None) or []
            for block in blocks:
                if isinstance(block, dict) and block.get('type') == 'reasoning':
                    return block.get('reasoning', '')
            return ''

        try:
            event_count = 0
            logger.info(f"[CHAT START] agent_id={agent_id} model={agent.model} provider={agent.provider} tools={len(tools) if tools else 0}")
            logger.debug(f"[CHAT MESSAGES] count={len(messages)} system_prompt_len={len(system_prompt)}")
            for i, m in enumerate(messages):
                role = getattr(m, 'type', 'unknown')
                content = getattr(m, 'content', '')
                logger.debug(f"  msg[{i}] {role}: {truncate_for_log(content, 200)}")

            if tools:
                # Use create_agent for full ReAct loop with streaming (LangGraph)
                agent_runnable = create_agent(
                    llm,
                    tools=tools,
                    system_prompt=system_prompt,
                )
                logger.info(f"[CHAT AGENT CREATED] tools={[t.name for t in tools]}")
                event_count = 0
                # Use astream_events for fine-grained, consistent event format
                async for event in agent_runnable.astream_events(
                    {"messages": messages},
                    version="v2",
                ):
                    event_count += 1
                    event_type = event.get("event")

                    # ── LLM streaming tokens ──
                    if event_type == "on_chat_model_stream":
                        chunk = event["data"]["chunk"]
                        # Normalize ChatGenerationChunk -> AIMessageChunk
                        if hasattr(chunk, "message") and chunk.message is not None:
                            msg_chunk = chunk.message
                        elif hasattr(chunk, "content"):
                            msg_chunk = chunk
                        else:
                            continue

                        if not isinstance(msg_chunk, (AIMessage, AIMessageChunk)):
                            continue

                        # Stream reasoning content
                        reasoning = _extract_reasoning(msg_chunk)
                        if reasoning:
                            reasoning_buffer += reasoning
                            logger.debug(f"[CHAT STREAM] reasoning={truncate_for_log(reasoning, 200)}")
                            yield f"data: {json.dumps({'reasoning': reasoning}, ensure_ascii=False)}\n\n"

                        # Stream text content
                        if msg_chunk.content:
                            full_response += msg_chunk.content
                            logger.debug(f"[CHAT STREAM] content={truncate_for_log(msg_chunk.content, 200)}")
                            yield f"data: {json.dumps({'content': msg_chunk.content}, ensure_ascii=False)}\n\n"

                    # ── LLM call finished (tool_calls appear here) ──
                    elif event_type == "on_chat_model_end":
                        output = event["data"]["output"]
                        # Normalize ChatResult / AIMessage -> AIMessage
                        if hasattr(output, "generations") and output.generations:
                            msg = output.generations[0].message
                        elif isinstance(output, AIMessage):
                            msg = output
                        else:
                            continue

                        # Notify about tool calls
                        valid_tool_calls = [tc for tc in (msg.tool_calls or []) if tc.get("name")]
                        if valid_tool_calls:
                            tool_names = [tc["name"] for tc in valid_tool_calls]
                            tool_args = [tc.get("args", {}) for tc in valid_tool_calls]
                            logger.info(f"[CHAT TOOL CALL] names={tool_names} args={truncate_for_log(tool_args, 500)}")
                            yield f"data: {json.dumps({'tool_calls': tool_names}, ensure_ascii=False)}\n\n"
                            # Send detailed browser events for frontend panel
                            for tc in valid_tool_calls:
                                if tc["name"].startswith("browser_"):
                                    yield f"data: {json.dumps({'browser_event': {'name': tc['name'], 'args': tc.get('args', {})}}, ensure_ascii=False)}\n\n"
                                    # Send browser_status to show active browsing indicator
                                    if tc["name"] == "browser_navigate":
                                        url = tc.get("args", {}).get("url", "")
                                        yield f"data: {json.dumps({'browser_status': {'state': 'navigating', 'url': url}}, ensure_ascii=False)}\n\n"
                                    elif tc["name"] == "browser_get_text":
                                        yield f"data: {json.dumps({'browser_status': {'state': 'reading'}}, ensure_ascii=False)}\n\n"
            else:
                # No tools: simple LLM streaming (token-level)
                logger.info("[CHAT STREAM] No tools, direct LLM streaming")
                chunk_count = 0
                async for chunk in llm.astream(messages):
                    chunk_count += 1
                    # Stream reasoning content (incremental tokens from provider)
                    reasoning = _extract_reasoning(chunk)
                    if reasoning:
                        reasoning_buffer += reasoning
                        logger.debug(f"[CHAT STREAM] reasoning_chunk={truncate_for_log(reasoning, 200)}")
                        yield f"data: {json.dumps({'reasoning': reasoning}, ensure_ascii=False)}\n\n"

                    # Stream text content
                    if chunk.content:
                        full_response += chunk.content
                        logger.debug(f"[CHAT STREAM] content_chunk={truncate_for_log(chunk.content, 200)}")
                        yield f"data: {json.dumps({'content': chunk.content}, ensure_ascii=False)}\n\n"
                logger.info(f"[CHAT STREAM] Finished. chunks={chunk_count} total_content_len={len(full_response)}")

            # Save final response
            if full_response:
                append_chat_message(agent_id, "assistant", full_response)
                if group_id:
                    append_group_chat_message(group_id, "assistant", agent_id, agent.name, full_response)
                logger.info(f"[CHAT SAVED] agent_id={agent_id} response_len={len(full_response)} reasoning_len={len(reasoning_buffer)}")

        except Exception as e:
            logger.exception(f"[CHAT ERROR] agent_id={agent_id} error={e}")
            error_msg = f"[Error: {e}]"
            yield f"data: {json.dumps({'error': error_msg}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"
        logger.info(f"[CHAT DONE] agent_id={agent_id} events={event_count if 'event_count' in locals() else 'N/A'}")

    return StreamingResponse(stream_response(), media_type="text/event-stream")
