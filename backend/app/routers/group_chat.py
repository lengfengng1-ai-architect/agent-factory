"""Group chat with parallel brainstorm, debate, and moderator modes."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app import redis_client
from app.file_utils import extract_text, format_files_for_prompt, is_image_file, image_to_base64
from app.context_manager import build_messages_with_budget, get_model_context_window
from app.summarizer import generate_summary, maybe_use_summary, get_summaries_for_group
from app.llm_factory import create_llm
from app.common import get_agent_provider
from app.tools import get_agent_tools, run_llm_with_tools
from langchain.messages import HumanMessage, SystemMessage, AIMessage
from pydantic import BaseModel, Field
import json

router = APIRouter()


def _inject_files_into_user_message(user_message: str, file_contents: list[dict]) -> str:
    """Prepend file contents to user message."""
    if not file_contents:
        return user_message
    files_prompt = format_files_for_prompt(file_contents)
    return f"{files_prompt}\n用户问题：{user_message}"


def _build_agent_messages(agent: models.Agent, history: list, file_contents: list[dict] = None):
    """Build message list for an agent including group history and file attachments."""
    messages = [SystemMessage(content=agent.system_prompt or "You are a helpful assistant.")]

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


async def _load_group_file_contents(
    group_id: int,
    file_ids: list[str],
    file_mode: str,
    db: Session,
) -> tuple[list[dict], list[dict]]:
    """Load file contents for a group chat, generating summaries if needed.

    Returns:
        (file_contents, image_attachments)
    """
    if not file_ids:
        return [], []

    uploaded_files = redis_client.get_group_chat_files(group_id)
    file_id_to_meta = {f.get("id"): f for f in uploaded_files}

    file_contents = []
    image_attachments = []
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    fallback_agent = None
    fallback_provider = None
    if group and group.agent_ids:
        for aid in group.agent_ids:
            agent = db.query(models.Agent).filter(models.Agent.id == aid).first()
            if not agent:
                continue
            try:
                fallback_provider = get_agent_provider(db, agent)
                fallback_agent = agent
                break
            except ValueError:
                continue

    for fid in file_ids:
        meta = file_id_to_meta.get(fid)
        if not meta:
            continue
        path = meta.get("path", "")
        name = meta.get("name", "unknown")
        if not path:
            continue

        # Image files → multimodal
        if is_image_file(path):
            try:
                b64, mime = image_to_base64(path)
                image_attachments.append({"file_id": fid, "name": name, "base64": b64, "mime_type": mime})
            except Exception:
                pass
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

    return file_contents, image_attachments


@router.get("/{group_id}/chat/history")
def get_group_chat_history_endpoint(group_id: int, db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"messages": redis_client.get_group_chat_history(group_id)}


class GroupChatPayload(BaseModel):
    message: str = Field(..., description="User message text")
    files: list[str] = Field(default_factory=list, description="List of file IDs to attach")
    file_mode: str = Field(default="auto", description="File processing mode: auto, truncate, summary")


@router.post("/{group_id}/chat")
async def group_chat(group_id: int, payload: GroupChatPayload, db: Session = Depends(get_db)):
    group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    chat_type = group.chat_type or "parallel"
    user_message = payload.message
    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")

    file_ids = payload.files or []
    file_mode = payload.file_mode or "auto"

    file_contents, image_attachments = await _load_group_file_contents(group_id, file_ids, file_mode, db)

    # Load historical summaries for this group (up to 5 most recent)
    historical_summaries = get_summaries_for_group(group.id)
    if historical_summaries:
        for hs in historical_summaries[:5]:
            file_contents.append({
                "name": hs["file_name"] + "（历史摘要）",
                "content": hs["summary"],
                "is_summary": True,
            })

    attachments = [{"type": "image", "file_id": img["file_id"], "name": img["name"]} for img in image_attachments]

    if chat_type == "brainstorm":
        return _brainstorm_chat(group, user_message, db, file_contents, image_attachments, attachments)
    elif chat_type == "debate":
        return _debate_chat(group, user_message, db, file_contents, image_attachments, attachments)
    elif chat_type == "moderator":
        return _moderator_chat(group, user_message, db, file_contents, image_attachments, attachments)
    else:
        raise HTTPException(status_code=400, detail="Parallel mode should use individual agent chat API")


# ──────────────────────────────────────────────────────────────
# Brainstorm — parallel execution with asyncio.gather
# ──────────────────────────────────────────────────────────────

def _brainstorm_chat(group, user_message, db, file_contents: list[dict] = None, image_attachments: list[dict] = None, attachments: list[dict] = None):
    redis_client.append_group_chat_message(group.id, "user", 0, "User", user_message, attachments=attachments or None)

    agent_ids = group.agent_ids or []
    if not agent_ids:
        raise HTTPException(status_code=400, detail="Group has no agents")

    async def stream():
        history = redis_client.get_group_chat_history(group.id)

        # Build agent configs in parallel
        agent_configs = []
        for agent_id in agent_ids:
            agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
            if not agent:
                continue
            try:
                provider = get_agent_provider(db, agent)
                agent_configs.append((agent, provider))
            except ValueError:
                continue

        # Execute all agents in parallel
        async def _run_agent(agent, provider):
            context_window = get_model_context_window(db, agent)
            messages = build_messages_with_budget(
                agent=agent,
                history=history,
                user_message=user_message,
                file_contents=file_contents or [],
                context_window=context_window,
                image_attachments=image_attachments or None,
            )
            llm = create_llm(agent, provider, streaming=False)
            tools = get_agent_tools(agent, override_root_dir=group.file_root_dir or None)
            content = await run_llm_with_tools(llm, messages, tools)
            return {"agent": agent, "content": content}

        results = await asyncio.gather(
            *[_run_agent(a, p) for a, p in agent_configs],
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, Exception):
                yield f"data: {json.dumps({'error': str(result)}, ensure_ascii=False)}\n\n"
                continue
            agent = result["agent"]
            content = result["content"]
            yield f"data: {json.dumps({'agent_id': agent.id, 'agent_name': agent.name, 'content': content, 'done': False}, ensure_ascii=False)}\n\n"
            redis_client.append_group_chat_message(group.id, "assistant", agent.id, agent.name, content)
            yield f"data: {json.dumps({'agent_id': agent.id, 'agent_name': agent.name, 'content': '', 'done': True}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ──────────────────────────────────────────────────────────────
# Debate — sequential rounds with structured output summary
# ──────────────────────────────────────────────────────────────

def _build_debate_messages(agent: models.Agent, history: list, side: str, round_num: int, file_contents: list[dict] = None, image_attachments: list[dict] = None):
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
        if image_attachments:
            multimodal = [{"type": "text", "text": content}]
            for img in image_attachments:
                url = f"data:{img['mime_type']};base64,{img['base64']}"
                multimodal.append({"type": "image_url", "image_url": {"url": url}})
            messages.append(HumanMessage(content=multimodal))
        else:
            messages.append(HumanMessage(content=content))

    return messages


def _build_summary_prompt(history: list) -> str:
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


def _debate_chat(group, user_message, db, file_contents: list[dict] = None, image_attachments: list[dict] = None, attachments: list[dict] = None):
    agent_ids = group.agent_ids or []
    if len(agent_ids) < 2:
        raise HTTPException(status_code=400, detail="Debate mode requires at least 2 agents")

    debate_cfg = (group.config or {}).get("debate", {})
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

    redis_client.append_group_chat_message(group.id, "user", 0, "User", user_message, attachments=attachments or None)

    async def stream():
        history = redis_client.get_group_chat_history(group.id)

        for r in range(rounds):
            for side, side_ids in [("正方", pro_ids), ("反方", con_ids)]:
                agent_idx = r % len(side_ids)
                agent_id = side_ids[agent_idx]

                agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
                if not agent:
                    continue

                try:
                    provider = get_agent_provider(db, agent)
                except ValueError:
                    continue

                messages = _build_debate_messages(agent, history, side, r + 1, file_contents, image_attachments)
                llm = create_llm(agent, provider, streaming=False)
                tools = get_agent_tools(agent, override_root_dir=group.file_root_dir or None)
                content = await run_llm_with_tools(llm, messages, tools)
                full_response = content
                yield f"data: {json.dumps({'agent_id': agent.id, 'agent_name': f'{agent.name} ({side})', 'content': content, 'done': False, 'round': r+1, 'side': side}, ensure_ascii=False)}\n\n"

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
                try:
                    provider = get_agent_provider(db, summary_agent)
                except ValueError:
                    provider = None
                if provider:
                    summary_prompt = _build_summary_prompt(
                        redis_client.get_group_chat_history(group.id)
                    )
                    messages = [
                        SystemMessage(
                            content=summary_agent.system_prompt or "You are a helpful assistant."
                        ),
                        HumanMessage(content=summary_prompt),
                    ]
                    llm = create_llm(summary_agent, provider, streaming=False)
                    tools = get_agent_tools(summary_agent, override_root_dir=group.file_root_dir or None)
                    content = await run_llm_with_tools(llm, messages, tools)
                    full_response = content
                    yield f"data: {json.dumps({'agent_id': summary_agent.id, 'agent_name': f'{summary_agent.name} (总结)', 'content': content, 'done': False, 'round': rounds+1, 'phase': 'summary'}, ensure_ascii=False)}\n\n"

                    redis_client.append_group_chat_message(
                        group.id, "assistant", summary_agent.id,
                        f"{summary_agent.name} (总结)", full_response
                    )
                    yield f"data: {json.dumps({'agent_id': summary_agent.id, 'agent_name': f'{summary_agent.name} (总结)', 'content': '', 'done': True, 'round': rounds+1, 'phase': 'summary'}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


# ──────────────────────────────────────────────────────────────
# Moderator — experts + summary
# ──────────────────────────────────────────────────────────────

def _build_moderator_expert_messages(agent: models.Agent, user_message: str, file_contents: list[dict] = None, image_attachments: list[dict] = None):
    system_prompt = agent.system_prompt or "You are a helpful assistant."
    expert_context = (
        "\n\n【任务说明】你是一名领域专家。主持人向你提出了一个问题/议题，"
        "请你基于专业知识给出结构化、有深度的回答。"
        "请尽量覆盖问题的关键维度，并给出明确的观点和理由。"
        "回答应当条理清晰，有逻辑性。"
    )
    content = _inject_files_into_user_message(user_message, file_contents or [])
    if image_attachments:
        multimodal = [{"type": "text", "text": content}]
        for img in image_attachments:
            url = f"data:{img['mime_type']};base64,{img['base64']}"
            multimodal.append({"type": "image_url", "image_url": {"url": url}})
        return [
            SystemMessage(content=system_prompt + expert_context),
            HumanMessage(content=multimodal),
        ]
    return [
        SystemMessage(content=system_prompt + expert_context),
        HumanMessage(content=content),
    ]


def _build_moderator_summary_prompt(user_message: str, expert_responses: list) -> str:
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


def _moderator_chat(group, user_message, db, file_contents: list[dict] = None, image_attachments: list[dict] = None, attachments: list[dict] = None):
    agent_ids = group.agent_ids or []
    if not agent_ids:
        raise HTTPException(status_code=400, detail="Group has no agents")

    mod_cfg = (group.config or {}).get("moderator", {})
    moderator_id = mod_cfg.get("moderator_id")
    if not moderator_id and agent_ids:
        moderator_id = agent_ids[0]

    expert_ids = [aid for aid in agent_ids if aid != moderator_id]

    redis_client.append_group_chat_message(group.id, "user", 0, "User", user_message, attachments=attachments or None)

    async def stream():
        # Phase 1: Experts respond (parallel!)
        async def _run_expert(agent_id):
            agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
            if not agent:
                return None
            try:
                provider = get_agent_provider(db, agent)
            except ValueError:
                return None

            llm = create_llm(agent, provider, streaming=False)
            tools = get_agent_tools(agent, override_root_dir=group.file_root_dir or None)
            messages = _build_moderator_expert_messages(agent, user_message, file_contents, image_attachments)

            content = await run_llm_with_tools(llm, messages, tools)
            return {"agent": agent, "content": content}

        expert_results = await asyncio.gather(
            *[_run_expert(aid) for aid in expert_ids],
            return_exceptions=True,
        )

        expert_responses = []
        for result in expert_results:
            if isinstance(result, Exception) or result is None:
                continue
            agent = result["agent"]
            content = result["content"]
            yield f"data: {json.dumps({'phase': 'expert', 'agent_id': agent.id, 'agent_name': agent.name, 'content': content, 'done': False}, ensure_ascii=False)}\n\n"
            expert_responses.append({"agent_id": agent.id, "agent_name": agent.name, "response": content})
            redis_client.append_group_chat_message(group.id, "assistant", agent.id, agent.name, content)
            yield f"data: {json.dumps({'phase': 'expert', 'agent_id': agent.id, 'agent_name': agent.name, 'content': '', 'done': True}, ensure_ascii=False)}\n\n"

        # Phase 2: Moderator summarizes
        moderator = db.query(models.Agent).filter(models.Agent.id == moderator_id).first()
        if moderator and expert_responses:
            try:
                provider = get_agent_provider(db, moderator)
            except ValueError:
                provider = None
            if provider:
                summary_prompt = _build_moderator_summary_prompt(user_message, expert_responses)

                llm = create_llm(moderator, provider, streaming=False)
                tools = get_agent_tools(moderator, override_root_dir=group.file_root_dir or None)
                messages = [
                    SystemMessage(
                        content=moderator.system_prompt or "You are a helpful assistant."
                    ),
                    HumanMessage(content=summary_prompt),
                ]

                content = await run_llm_with_tools(llm, messages, tools)
                full_response = content
                yield f"data: {json.dumps({'phase': 'moderator', 'agent_id': moderator.id, 'agent_name': moderator.name, 'content': content, 'done': False}, ensure_ascii=False)}\n\n"

                redis_client.append_group_chat_message(
                    group.id, "assistant", moderator.id, moderator.name, full_response
                )
                yield f"data: {json.dumps({'phase': 'moderator', 'agent_id': moderator.id, 'agent_name': moderator.name, 'content': '', 'done': True}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
