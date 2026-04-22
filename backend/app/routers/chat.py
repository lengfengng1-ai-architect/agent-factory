import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.redis_client import (
    get_chat_history, append_chat_message, append_group_chat_message,
    set_chat_partial, get_chat_partial, delete_chat_partial,
    get_chat_files,
)
from app.file_utils import extract_text
from app.context_manager import build_messages_with_budget, get_model_context_window
from app.summarizer import generate_summary, maybe_use_summary, get_summaries_for_agent
from app.tools import get_agent_tools
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
import json
import os

router = APIRouter()

# Track background generation tasks per agent
_generating_tasks: dict[int, asyncio.Task] = {}


@router.get("/{agent_id}/chat/history")
def get_agent_chat_history(agent_id: int):
    return {"messages": get_chat_history(agent_id)}


@router.post("/{agent_id}/chat")
async def chat_with_agent(agent_id: int, payload: dict, db: Session = Depends(get_db)):
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    user_message = payload.get("message", "")
    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")

    system_prompt = agent.system_prompt or "You are a helpful assistant."

    provider = db.query(models.Provider).filter(
        models.Provider.key == (agent.provider or "kimi").lower()
    ).first()
    if not provider:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {agent.provider}")
    if not provider.is_enabled:
        raise HTTPException(status_code=400, detail=f"Provider {provider.name} is disabled")

    base_url = provider.base_url
    model = agent.model or ""
    api_key = agent.api_key or ""

    if provider.key == "custom":
        base_url = agent.api_url or base_url
        model = agent.model
        if not api_key:
            raise HTTPException(status_code=400, detail="Agent api_key not configured")
    else:
        if not base_url:
            raise HTTPException(status_code=400, detail="Provider base_url not configured")
        if not model:
            raise HTTPException(status_code=400, detail="Agent model not configured")
        if provider.key == "ollama":
            api_key = api_key or "ollama"
        elif not api_key:
            raise HTTPException(status_code=400, detail="Agent api_key not configured")

    # Save user message
    append_chat_message(agent_id, "user", user_message)
    group_id = payload.get("group_id")
    if group_id:
        from app.database import get_db as get_db_local
        db_local = next(get_db_local())
        try:
            agent = db_local.query(models.Agent).filter(models.Agent.id == agent_id).first()
            if agent:
                append_group_chat_message(group_id, "user", 0, "User", user_message)
        finally:
            db_local.close()

    # Build messages with history and file attachments
    history = get_chat_history(agent_id)

    # Load file contents
    file_ids = payload.get("files", []) or []
    file_mode = payload.get("file_mode", "auto")  # "auto" | "truncate" | "summary"
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

            # If summary is needed but not cached, generate it now
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
                    pass  # fallback to full/truncated content

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

    # Get context window and build budget-constrained messages
    context_window = get_model_context_window(db, agent)
    messages = build_messages_with_budget(
        agent=agent,
        history=history,
        user_message=user_message,
        file_contents=file_contents,
        context_window=context_window,
    )

    # Determine file root directory
    override_root = None
    if group_id:
        group = db.query(models.Group).filter(models.Group.id == group_id).first()
        if group and group.file_root_dir:
            override_root = group.file_root_dir

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        streaming=True,
    )

    async def _background_generate(
        agent_id: int,
        msgs: list,
        llm_instance: ChatOpenAI,
        group_id: int | None,
        agent_name: str,
        override_root: str | None,
    ):
        """Run LLM generation in background, saving partial results to Redis."""
        full_response = ""
        try:
            tools = get_agent_tools(agent, override_root_dir=override_root)

            if tools:
                llm_with_tools = llm_instance.bind_tools(tools)
                response = await llm_with_tools.ainvoke(msgs)

                if response.tool_calls:
                    msgs.append(response)
                    for tool_call in response.tool_calls:
                        tool = next((t for t in tools if t.name == tool_call["name"]), None)
                        if tool:
                            try:
                                result = await tool.ainvoke(tool_call["args"])
                            except Exception as e:
                                result = f"Error executing tool: {e}"
                        else:
                            result = f"Tool '{tool_call['name']}' not found"
                        msgs.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

                    async for chunk in llm_with_tools.astream(msgs):
                        text = chunk.content
                        if text:
                            full_response += text
                            set_chat_partial(agent_id, full_response)
                else:
                    async for chunk in llm_with_tools.astream(msgs):
                        text = chunk.content
                        if text:
                            full_response += text
                            set_chat_partial(agent_id, full_response)
            else:
                async for chunk in llm_instance.astream(msgs):
                    text = chunk.content
                    if text:
                        full_response += text
                        set_chat_partial(agent_id, full_response)

            # Save final complete response
            append_chat_message(agent_id, "assistant", full_response)
            if group_id:
                append_group_chat_message(group_id, "assistant", agent_id, agent_name, full_response)
        except asyncio.CancelledError:
            # Generation was cancelled (e.g. user sent a new message)
            raise
        finally:
            delete_chat_partial(agent_id)
            _generating_tasks.pop(agent_id, None)

    # Cancel any existing generation for this agent
    existing_task = _generating_tasks.get(agent_id)
    if existing_task and not existing_task.done():
        existing_task.cancel()
        try:
            await existing_task
        except asyncio.CancelledError:
            pass
        delete_chat_partial(agent_id)

    # Start new background generation task
    task = asyncio.create_task(
        _background_generate(agent_id, messages, llm, group_id, agent.name, override_root)
    )
    _generating_tasks[agent_id] = task

    async def stream():
        """Stream generation progress from background task."""
        last_len = 0

        while True:
            partial = get_chat_partial(agent_id)
            if partial and len(partial) > last_len:
                new_text = partial[last_len:]
                last_len = len(partial)
                yield f"data: {json.dumps({'content': new_text}, ensure_ascii=False)}\n\n"

            current_task = _generating_tasks.get(agent_id)
            if current_task and current_task.done():
                # Send any remaining content
                partial = get_chat_partial(agent_id)
                if partial and len(partial) > last_len:
                    new_text = partial[last_len:]
                    yield f"data: {json.dumps({'content': new_text}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                break

            await asyncio.sleep(0.2)

    return StreamingResponse(stream(), media_type="text/event-stream")
