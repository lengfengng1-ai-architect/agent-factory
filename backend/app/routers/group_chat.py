"""Group chat with file attachment support and context budget management."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app import redis_client
from app.file_utils import extract_text, format_files_for_prompt
from app.context_manager import build_messages_with_budget, get_model_context_window
from app.summarizer import generate_summary, maybe_use_summary
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


def _inject_files_into_user_message(user_message: str, file_contents: list[dict]) -> str:
    """Prepend file contents to user message."""
    if not file_contents:
        return user_message
    files_prompt = format_files_for_prompt(file_contents)
    return f"{files_prompt}\n用户问题：{user_message}"


def _build_agent_messages(agent: models.Agent, history: list, file_contents: list[dict] = None):
    """Build message list for an agent including group history and file attachments."""
    messages = [SystemMessage(content=agent.system_prompt or "You are a helpful assistant.")]

    for msg in history[:-1]:  # Exclude last user message
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            prefix = f"[{msg.get('agent_name', 'Agent')}]: "
            messages.append(AIMessage(content=prefix + msg["content"]))

    if history and history[-1]["role"] == "user":
        content = _inject_files_into_user_message(history[-1]["content"], file_contents or [])
        messages.append(HumanMessage(content=content))

    return messages


async def _load_group_file_contents(
    group_id: int,
    file_ids: list[str],
    file_mode: str,
    db: Session,
) -> list[dict]:
    """Load file contents for a group chat, generating summaries if needed."""
    if not file_ids:
        return []

    uploaded_files = redis_client.get_group_chat_files(group_id)
    file_id_to_meta = {f.get("id"): f for f in uploaded_files}

    file_contents = []
    # For summary generation fallback, pick the first available agent's provider
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    fallback_agent = None
    fallback_provider = None
    if group and group.agent_ids:
        for aid in group.agent_ids:
            agent = db.query(models.Agent).filter(models.Agent.id == aid).first()
            if not agent:
                continue
            provider = db.query(models.Provider).filter(
                models.Provider.key == (agent.provider or "kimi").lower()
            ).first()
            if provider and provider.is_enabled:
                fallback_agent = agent
                fallback_provider = provider
                break

    for fid in file_ids:
        meta = file_id_to_meta.get(fid)
        if not meta:
            continue
        path = meta.get("path", "")
        name = meta.get("name", "unknown")
        if not path:
            continue

        result = maybe_use_summary(path, name, file_mode)
        content = result.get("content", "")
        is_summary = result.get("is_summary", False)

        if result.get("needs_summary") and fallback_agent and fallback_provider:
            try:
                summary = await asyncio.wait_for(
                    generate_summary(path, name, fallback_agent, fallback_provider),
                    timeout=15,
                )
                if not summary.startswith("["):
                    content = summary
                    is_summary = True
            except asyncio.TimeoutError:
                pass

        file_contents.append({"name": name, "content": content, "is_summary": is_summary})

    return file_contents


@router.get("/{group_id}/chat/history")
def get_group_chat_history_endpoint(group_id: int, db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    chat_type = group.chat_type or "parallel"

    # All chat types use group-level chat history (isolated from individual agent chats)
    return {"messages": redis_client.get_group_chat_history(group_id)}


@router.post("/{group_id}/chat")
async def group_chat(group_id: int, payload: dict, db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    chat_type = group.chat_type or "parallel"
    user_message = payload.get("message", "")
    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")

    file_ids = payload.get("files", []) or []
    file_mode = payload.get("file_mode", "auto")

    # Preload file contents (with async summary generation)
    file_contents = await _load_group_file_contents(group_id, file_ids, file_mode, db)

    if chat_type == "brainstorm":
        return _brainstorm_chat(group, user_message, db, file_contents)
    elif chat_type == "debate":
        return _debate_chat(group, user_message, db, file_contents)
    elif chat_type == "moderator":
        return _moderator_chat(group, user_message, db, file_contents)
    else:
        raise HTTPException(status_code=400, detail="Parallel mode should use individual agent chat API")


def _brainstorm_chat(group, user_message, db, file_contents: list[dict] = None):
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

            # Use context budget management for each agent
            context_window = get_model_context_window(db, agent)
            messages = build_messages_with_budget(
                agent=agent,
                history=history,
                user_message=user_message,
                file_contents=file_contents or [],
                context_window=context_window,
            )

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


def _build_debate_messages(agent: models.Agent, history: list, side: str, round_num: int, file_contents: list[dict] = None):
    """Build messages for debate mode with context-aware prompts and file attachments."""
    system_prompt = agent.system_prompt or "You are a helpful assistant."
    debate_context = f"\n\n【辩论规则】你正在参与一场辩论，你的阵营是【{side}】。"
    if round_num > 1:
        debate_context += (
            f" 这是第{round_num}轮。请仔细回顾之前的辩论内容，"
            "针对性地回应对方的观点，同时捍卫和深化你的立场。"
        )
    else:
        debate_context += (
            " 这是第1轮，请首先清晰、有力地阐述你的立场和核心论点。"
        )
    debate_context += " 你的发言应当有逻辑性、有说服力。"

    messages = [SystemMessage(content=system_prompt + debate_context)]

    for msg in history[:-1]:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            prefix = f"[{msg.get('agent_name', 'Agent')}]: "
            messages.append(AIMessage(content=prefix + msg["content"]))

    if history and history[-1]["role"] == "user":
        content = _inject_files_into_user_message(history[-1]["content"], file_contents or [])
        messages.append(HumanMessage(content=content))

    return messages


def _build_summary_prompt(history: list) -> str:
    """Build summary prompt from debate history."""
    prompt = (
        "请作为辩论总结者，基于以下完整的辩论记录，给出一份公正、全面的总结。"
        "总结应包括：\n"
        "1. 各方的核心论点\n"
        "2. 辩论中的关键交锋点\n"
        "3. 你的综合评判\n\n"
        "【辩论记录】\n\n"
    )
    for msg in history:
        if msg["role"] == "user":
            prompt += f"[用户]: {msg['content']}\n"
        elif msg["role"] == "assistant":
            prompt += f"[{msg.get('agent_name', 'Agent')}]: {msg['content']}\n"
    prompt += "\n请给出你的总结："
    return prompt


def _debate_chat(group, user_message, db, file_contents: list[dict] = None):
    agent_ids = group.agent_ids or []
    if len(agent_ids) < 2:
        raise HTTPException(status_code=400, detail="Debate mode requires at least 2 agents")

    debate_cfg = (group.config or {}).get("debate", {})

    # Auto-assign compatibility when no config exists
    pro_ids = debate_cfg.get("pro_agent_ids", [])
    con_ids = debate_cfg.get("con_agent_ids", [])
    if not pro_ids and not con_ids:
        pro_ids = [agent_ids[0]]
        con_ids = agent_ids[1:]

    rounds = debate_cfg.get("rounds", 3)
    summary_agent_id = debate_cfg.get("summary_agent_id")

    if not pro_ids or not con_ids:
        raise HTTPException(
            status_code=400, detail="Debate mode requires at least one agent on each side"
        )

    redis_client.append_group_chat_message(group.id, "user", 0, "User", user_message)

    async def stream():
        history = redis_client.get_group_chat_history(group.id)

        for r in range(rounds):
            # Alternate: pro first, then con; rotate agents within each side
            for side, side_ids in [("正方", pro_ids), ("反方", con_ids)]:
                agent_idx = r % len(side_ids)
                agent_id = side_ids[agent_idx]

                agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
                if not agent:
                    continue

                provider = db.query(models.Provider).filter(
                    models.Provider.key == (agent.provider or "kimi").lower()
                ).first()
                if not provider or not provider.is_enabled:
                    continue

                messages = _build_debate_messages(agent, history, side, r + 1, file_contents)
                llm = _create_llm(agent, provider)
                full_response = ""

                async for chunk in llm.astream(messages):
                    text = chunk.content
                    if text:
                        full_response += text
                        yield f"data: {json.dumps({'agent_id': agent.id, 'agent_name': f'{agent.name} ({side})', 'content': text, 'done': False, 'round': r+1, 'side': side}, ensure_ascii=False)}\n\n"

                redis_client.append_group_chat_message(
                    group.id, "assistant", agent.id, f"{agent.name} ({side})", full_response
                )
                yield f"data: {json.dumps({'agent_id': agent.id, 'agent_name': f'{agent.name} ({side})', 'content': '', 'done': True, 'round': r+1, 'side': side}, ensure_ascii=False)}\n\n"
                history = redis_client.get_group_chat_history(group.id)

        # Summary phase
        if summary_agent_id:
            summary_agent = (
                db.query(models.Agent).filter(models.Agent.id == summary_agent_id).first()
            )
            if summary_agent:
                provider = db.query(models.Provider).filter(
                    models.Provider.key == (summary_agent.provider or "kimi").lower()
                ).first()
                if provider and provider.is_enabled:
                    summary_prompt = _build_summary_prompt(
                        redis_client.get_group_chat_history(group.id)
                    )
                    messages = [
                        SystemMessage(
                            content=summary_agent.system_prompt or "You are a helpful assistant."
                        ),
                        HumanMessage(content=summary_prompt),
                    ]
                    llm = _create_llm(summary_agent, provider)
                    full_response = ""

                    async for chunk in llm.astream(messages):
                        text = chunk.content
                        if text:
                            full_response += text
                            yield f"data: {json.dumps({'agent_id': summary_agent.id, 'agent_name': f'{summary_agent.name} (总结)', 'content': text, 'done': False, 'round': rounds+1, 'phase': 'summary'}, ensure_ascii=False)}\n\n"

                    redis_client.append_group_chat_message(
                        group.id, "assistant", summary_agent.id,
                        f"{summary_agent.name} (总结)", full_response
                    )
                    yield f"data: {json.dumps({'agent_id': summary_agent.id, 'agent_name': f'{summary_agent.name} (总结)', 'content': '', 'done': True, 'round': rounds+1, 'phase': 'summary'}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


def _build_moderator_expert_messages(agent: models.Agent, user_message: str, file_contents: list[dict] = None):
    """Build messages for expert in moderator mode with context-aware prompts and file attachments."""
    system_prompt = agent.system_prompt or "You are a helpful assistant."
    expert_context = (
        "\n\n【任务说明】你是一名领域专家。主持人向你提出了一个问题/议题，"
        "请你基于专业知识给出结构化、有深度的回答。"
        "请尽量覆盖问题的关键维度，并给出明确的观点和理由。"
        "回答应当条理清晰，有逻辑性。"
    )
    content = _inject_files_into_user_message(user_message, file_contents or [])
    return [
        SystemMessage(content=system_prompt + expert_context),
        HumanMessage(content=content),
    ]


def _build_moderator_summary_prompt(user_message: str, expert_responses: list) -> str:
    """Build summary prompt for moderator with structured output guidance."""
    prompt = (
        "你是一位经验丰富的主持人。以下是你向各位专家提出的问题以及他们的回答，"
        "请你综合各方意见，给出一份结构化的总结报告。\n\n"
        "总结报告请按以下结构撰写：\n"
        "1. 【各方核心观点】简要概括每位专家的核心论点\n"
        "2. 【共识与分歧】总结专家之间的共识点和主要分歧\n"
        "3. 【综合建议】基于专家意见，给出你的综合判断和建议\n\n"
        f"【议题】\n{user_message}\n\n"
        "【专家意见】\n\n"
    )
    for er in expert_responses:
        prompt += f"【{er['agent_name']}】\n{er['response']}\n\n"
    prompt += "请开始撰写总结报告："
    return prompt


def _moderator_chat(group, user_message, db, file_contents: list[dict] = None):
    agent_ids = group.agent_ids or []
    if not agent_ids:
        raise HTTPException(status_code=400, detail="Group has no agents")

    mod_cfg = (group.config or {}).get("moderator", {})
    moderator_id = mod_cfg.get("moderator_id")
    if not moderator_id and agent_ids:
        moderator_id = agent_ids[0]

    expert_ids = [aid for aid in agent_ids if aid != moderator_id]

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
            messages = _build_moderator_expert_messages(agent, user_message, file_contents)

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
                summary_prompt = _build_moderator_summary_prompt(user_message, expert_responses)

                llm = _create_llm(moderator, provider)
                messages = [
                    SystemMessage(
                        content=moderator.system_prompt or "You are a helpful assistant."
                    ),
                    HumanMessage(content=summary_prompt),
                ]

                full_response = ""
                async for chunk in llm.astream(messages):
                    text = chunk.content
                    if text:
                        full_response += text
                        yield f"data: {json.dumps({'phase': 'moderator', 'agent_id': moderator.id, 'agent_name': moderator.name, 'content': text, 'done': False}, ensure_ascii=False)}\n\n"

                redis_client.append_group_chat_message(
                    group.id, "assistant", moderator.id, moderator.name, full_response
                )
                yield f"data: {json.dumps({'phase': 'moderator', 'agent_id': moderator.id, 'agent_name': moderator.name, 'content': '', 'done': True}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
