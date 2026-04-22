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
from app.tools import get_agent_tools
from app.llm_factory import create_llm
from langchain.agents import create_agent
from langchain.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
import json
import os

router = APIRouter()


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

    provider = db.query(models.Provider).filter(
        models.Provider.key == (agent.provider or "kimi").lower()
    ).first()
    if not provider:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {agent.provider}")
    if not provider.is_enabled:
        raise HTTPException(status_code=400, detail=f"Provider {provider.name} is disabled")

    # Build LLM
    try:
        llm = create_llm(agent, provider, streaming=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    system_prompt = agent.system_prompt or "You are a helpful assistant."

    # Save user message
    append_chat_message(agent_id, "user", user_message)
    group_id = payload.get("group_id")
    if group_id:
        from app.database import get_db as get_db_local
        db_local = next(get_db_local())
        try:
            agent_obj = db_local.query(models.Agent).filter(models.Agent.id == agent_id).first()
            if agent_obj:
                append_group_chat_message(group_id, "user", 0, "User", user_message)
        finally:
            db_local.close()

    # Build messages with history and file attachments
    history = get_chat_history(agent_id)
    file_ids = payload.get("files", []) or []
    file_mode = payload.get("file_mode", "auto")
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

    tools = get_agent_tools(agent, override_root_dir=override_root)

    async def stream_response():
        """Stream agent response directly using agent.astream()."""
        full_response = ""

        try:
            if tools:
                # Use create_agent for full ReAct loop with streaming
                agent_runnable = create_agent(
                    llm,
                    tools=tools,
                    system_prompt=system_prompt,
                )
                async for event in agent_runnable.astream(
                    {"messages": messages},
                    stream_mode="messages",
                ):
                    # event is a message object (AIMessage, ToolMessage, etc.)
                    if isinstance(event, AIMessage) and event.content:
                        full_response += event.content
                        yield f"data: {json.dumps({'content': event.content}, ensure_ascii=False)}\n\n"
                    elif isinstance(event, AIMessage) and event.tool_calls:
                        # Optionally notify frontend about tool calls
                        tool_names = [tc["name"] for tc in event.tool_calls]
                        yield f"data: {json.dumps({'tool_calls': tool_names}, ensure_ascii=False)}\n\n"
            else:
                # No tools: simple LLM streaming
                async for chunk in llm.astream(messages):
                    if chunk.content:
                        full_response += chunk.content
                        yield f"data: {json.dumps({'content': chunk.content}, ensure_ascii=False)}\n\n"

            # Save final response
            if full_response:
                append_chat_message(agent_id, "assistant", full_response)
                if group_id:
                    append_group_chat_message(group_id, "assistant", agent_id, agent.name, full_response)

        except Exception as e:
            error_msg = f"[Error: {e}]"
            yield f"data: {json.dumps({'error': error_msg}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream_response(), media_type="text/event-stream")
