from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app import redis_client
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
import json

router = APIRouter()


def _create_llm(agent: models.Agent, provider: models.Provider):
    """Create a ChatOpenAI instance for an agent."""
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
        streaming=True,
    )


def _build_agent_messages(agent: models.Agent, history: list):
    """Build message list for an agent including group history."""
    messages = [SystemMessage(content=agent.system_prompt or "You are a helpful assistant.")]

    for msg in history[:-1]:  # Exclude last user message
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            prefix = f"[{msg.get('agent_name', 'Agent')}]: "
            messages.append(AIMessage(content=prefix + msg["content"]))

    if history and history[-1]["role"] == "user":
        messages.append(HumanMessage(content=history[-1]["content"]))

    return messages


@router.get("/{group_id}/chat/history")
def get_group_chat_history_endpoint(group_id: int, db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    chat_type = group.chat_type or "parallel"

    # All chat types use group-level chat history (isolated from individual agent chats)
    return {"messages": redis_client.get_group_chat_history(group_id)}


@router.post("/{group_id}/chat")
def group_chat(group_id: int, payload: dict, db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    chat_type = group.chat_type or "parallel"
    user_message = payload.get("message", "")
    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")

    if chat_type == "brainstorm":
        return _brainstorm_chat(group, user_message, db)
    elif chat_type == "debate":
        return _debate_chat(group, user_message, db)
    elif chat_type == "moderator":
        return _moderator_chat(group, user_message, db)
    else:
        raise HTTPException(status_code=400, detail="Parallel mode should use individual agent chat API")


def _brainstorm_chat(group, user_message, db):
    redis_client.append_group_chat_message(group.id, "user", 0, "User", user_message)

    agent_ids = group.agent_ids or []
    if not agent_ids:
        raise HTTPException(status_code=400, detail="Group has no agents")

    async def stream():
        history = redis_client.get_group_chat_history(group.id)

        for agent_id in agent_ids:
            agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
            if not agent:
                continue

            provider = db.query(models.Provider).filter(
                models.Provider.key == (agent.provider or "kimi").lower()
            ).first()
            if not provider or not provider.is_enabled:
                continue

            messages = _build_agent_messages(agent, history)
            llm = _create_llm(agent, provider)
            full_response = ""

            async for chunk in llm.astream(messages):
                text = chunk.content
                if text:
                    full_response += text
                    yield f"data: {json.dumps({'agent_id': agent.id, 'agent_name': agent.name, 'content': text, 'done': False}, ensure_ascii=False)}\n\n"

            redis_client.append_group_chat_message(group.id, "assistant", agent.id, agent.name, full_response)
            yield f"data: {json.dumps({'agent_id': agent.id, 'agent_name': agent.name, 'content': '', 'done': True}, ensure_ascii=False)}\n\n"
            history = redis_client.get_group_chat_history(group.id)

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


def _debate_chat(group, user_message, db):
    agent_ids = (group.agent_ids or [])[:2]
    if len(agent_ids) < 2:
        raise HTTPException(status_code=400, detail="Debate mode requires at least 2 agents")

    redis_client.append_group_chat_message(group.id, "user", 0, "User", user_message)

    async def stream():
        history = redis_client.get_group_chat_history(group.id)
        rounds = 3

        for r in range(rounds):
            for i, agent_id in enumerate(agent_ids):
                agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
                if not agent:
                    continue

                side = "正方" if i == 0 else "反方"
                provider = db.query(models.Provider).filter(
                    models.Provider.key == (agent.provider or "kimi").lower()
                ).first()
                if not provider or not provider.is_enabled:
                    continue

                messages = _build_agent_messages(agent, history)
                # Add debate context to the last user message
                if messages and isinstance(messages[-1], HumanMessage):
                    debate_prompt = f"【这是第{r+1}轮辩论，你是{side}。请针对辩题发表你的观点。】\n\n"
                    messages[-1] = HumanMessage(content=debate_prompt + messages[-1].content)

                llm = _create_llm(agent, provider)
                full_response = ""

                async for chunk in llm.astream(messages):
                    text = chunk.content
                    if text:
                        full_response += text
                        yield f"data: {json.dumps({'agent_id': agent.id, 'agent_name': f'{agent.name} ({side})', 'content': text, 'done': False, 'round': r+1}, ensure_ascii=False)}\n\n"

                redis_client.append_group_chat_message(group.id, "assistant", agent.id, f"{agent.name} ({side})", full_response)
                yield f"data: {json.dumps({'agent_id': agent.id, 'agent_name': f'{agent.name} ({side})', 'content': '', 'done': True, 'round': r+1}, ensure_ascii=False)}\n\n"
                history = redis_client.get_group_chat_history(group.id)

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


def _moderator_chat(group, user_message, db):
    agent_ids = group.agent_ids or []
    if not agent_ids:
        raise HTTPException(status_code=400, detail="Group has no agents")

    moderator_id = agent_ids[0]
    expert_ids = agent_ids[1:]

    redis_client.append_group_chat_message(group.id, "user", 0, "User", user_message)

    async def stream():
        # Phase 1: Experts respond
        expert_responses = []
        for agent_id in expert_ids:
            agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
            if not agent:
                continue

            provider = db.query(models.Provider).filter(
                models.Provider.key == (agent.provider or "kimi").lower()
            ).first()
            if not provider or not provider.is_enabled:
                continue

            llm = _create_llm(agent, provider)
            messages = [SystemMessage(content=agent.system_prompt or "You are a helpful assistant.")]
            messages.append(HumanMessage(content=user_message))

            response = ""
            async for chunk in llm.astream(messages):
                text = chunk.content
                if text:
                    response += text
                    yield f"data: {json.dumps({'phase': 'expert', 'agent_id': agent.id, 'agent_name': agent.name, 'content': text, 'done': False}, ensure_ascii=False)}\n\n"

            expert_responses.append({"agent_id": agent.id, "agent_name": agent.name, "response": response})
            redis_client.append_group_chat_message(group.id, "assistant", agent.id, agent.name, response)
            yield f"data: {json.dumps({'phase': 'expert', 'agent_id': agent.id, 'agent_name': agent.name, 'content': '', 'done': True}, ensure_ascii=False)}\n\n"

        # Phase 2: Moderator summarizes
        moderator = db.query(models.Agent).filter(models.Agent.id == moderator_id).first()
        if moderator and expert_responses:
            provider = db.query(models.Provider).filter(
                models.Provider.key == (moderator.provider or "kimi").lower()
            ).first()
            if provider and provider.is_enabled:
                summary_prompt = "请作为主持人，综合以下专家意见，给出一份清晰的总结：\n\n"
                for er in expert_responses:
                    summary_prompt += f"【{er['agent_name']}】: {er['response']}\n\n"

                llm = _create_llm(moderator, provider)
                messages = [SystemMessage(content=moderator.system_prompt or "You are a helpful assistant.")]
                messages.append(HumanMessage(content=summary_prompt))

                full_response = ""
                async for chunk in llm.astream(messages):
                    text = chunk.content
                    if text:
                        full_response += text
                        yield f"data: {json.dumps({'phase': 'moderator', 'agent_id': moderator.id, 'agent_name': moderator.name + ' (主持人)', 'content': text, 'done': False}, ensure_ascii=False)}\n\n"

                redis_client.append_group_chat_message(group.id, "assistant", moderator.id, moderator.name + " (主持人)", full_response)
                yield f"data: {json.dumps({'phase': 'moderator', 'agent_id': moderator.id, 'agent_name': moderator.name + ' (主持人)', 'content': '', 'done': True}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
