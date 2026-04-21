from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.redis_client import get_chat_history, append_chat_message, append_group_chat_message
from app.tools import get_agent_tools
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
import json

router = APIRouter()


@router.get("/{agent_id}/chat/history")
def get_agent_chat_history(agent_id: int):
    return {"messages": get_chat_history(agent_id)}


@router.post("/{agent_id}/chat")
def chat_with_agent(agent_id: int, payload: dict, db: Session = Depends(get_db)):
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

    # Build messages with history
    history = get_chat_history(agent_id)
    messages = [SystemMessage(content=system_prompt)]
    for msg in history[:-1]:  # Exclude the just-added user message
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=user_message))

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        streaming=True,
    )

    async def stream():
        tools = get_agent_tools(agent)

        if tools:
            llm_with_tools = llm.bind_tools(tools)
            # First call: detect tool calls
            response = await llm_with_tools.ainvoke(messages)

            if response.tool_calls:
                messages.append(response)
                for tool_call in response.tool_calls:
                    tool = next((t for t in tools if t.name == tool_call["name"]), None)
                    if tool:
                        try:
                            result = await tool.ainvoke(tool_call["args"])
                        except Exception as e:
                            result = f"Error executing tool: {e}"
                    else:
                        result = f"Tool '{tool_call['name']}' not found"
                    messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

                # Second call: stream final answer after tool execution
                full_response = ""
                async for chunk in llm_with_tools.astream(messages):
                    text = chunk.content
                    if text:
                        full_response += text
                        yield f"data: {json.dumps({'content': text}, ensure_ascii=False)}\n\n"
                append_chat_message(agent_id, "assistant", full_response)
                if group_id:
                    append_group_chat_message(group_id, "assistant", agent_id, agent.name, full_response)
                yield "data: [DONE]\n\n"
                return

            # No tool calls but tools enabled: stream normally
            full_response = ""
            async for chunk in llm_with_tools.astream(messages):
                text = chunk.content
                if text:
                    full_response += text
                    yield f"data: {json.dumps({'content': text}, ensure_ascii=False)}\n\n"
            append_chat_message(agent_id, "assistant", full_response)
            if group_id:
                append_group_chat_message(group_id, "assistant", agent_id, agent.name, full_response)
            yield "data: [DONE]\n\n"
            return

        # No tools: existing logic
        full_response = ""
        async for chunk in llm.astream(messages):
            text = chunk.content
            if text:
                full_response += text
                yield f"data: {json.dumps({'content': text}, ensure_ascii=False)}\n\n"
        append_chat_message(agent_id, "assistant", full_response)
        if group_id:
            append_group_chat_message(group_id, "assistant", agent_id, agent.name, full_response)
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
