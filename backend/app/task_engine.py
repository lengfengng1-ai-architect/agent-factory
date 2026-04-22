import asyncio
from typing import Optional
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from app.tools import get_agent_tools, run_llm_with_tools
from app import models
from app.database import SessionLocal

MAX_CONCURRENT_TASKS = 3
_semaphore: asyncio.Semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
_executing_tasks: dict[int, asyncio.Task] = {}


def _create_llm_for_agent(agent: models.Agent, provider: models.Provider):
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
    )


async def _execute_with_agent(task: models.Task, db: Session):
    agent = db.query(models.Agent).filter(models.Agent.id == task.assignee_id).first()
    if not agent:
        return "Error: Agent not found"

    provider = db.query(models.Provider).filter(
        models.Provider.key == (agent.provider or "kimi").lower()
    ).first()
    if not provider or not provider.is_enabled:
        return "Error: Provider not available"

    llm = _create_llm_for_agent(agent, provider)
    tools = get_agent_tools(agent, override_root_dir=task.file_root_dir or None)
    messages = [
        SystemMessage(content=agent.system_prompt or "You are a helpful assistant."),
        HumanMessage(content=task.description or task.title),
    ]

    try:
        return await run_llm_with_tools(llm, messages, tools)
    except Exception as e:
        return f"Error: {e}"


def _build_moderator_summary_prompt(task_description: str, expert_responses: list) -> str:
    prompt = (
        "你是一位经验丰富的主持人。以下是各位专家针对议题给出的回答，"
        "请你综合各方意见，给出一份结构化的总结报告。\n\n"
        "总结报告请按以下结构撰写：\n"
        "1. 【各方核心观点】简要概括每位专家的核心论点\n"
        "2. 【共识与分歧】总结专家之间的共识点和主要分歧\n"
        "3. 【综合建议】基于专家意见，给出你的综合判断和建议\n\n"
        f"【议题】\n{task_description}\n\n"
        "【专家意见】\n\n"
    )
    for er in expert_responses:
        prompt += f"【{er['agent_name']}】\n{er['response']}\n\n"
    prompt += "请开始撰写总结报告："
    return prompt


async def _execute_with_group(task: models.Task, db: Session):
    group = db.query(models.Group).filter(models.Group.id == task.assignee_id).first()
    if not group:
        return "Error: Group not found"

    agent_ids = group.agent_ids or []
    if not agent_ids:
        return "Error: Group has no agents"

    mod_cfg = (group.config or {}).get("moderator", {})
    moderator_id = mod_cfg.get("moderator_id")
    if not moderator_id and agent_ids:
        moderator_id = agent_ids[0]

    expert_ids = [aid for aid in agent_ids if aid != moderator_id]
    task_prompt = task.description or task.title

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

        llm = _create_llm_for_agent(agent, provider)
        tools = get_agent_tools(agent, override_root_dir=task.file_root_dir or None)
        expert_context = (
            "\n\n【任务说明】你是一名领域专家。主持人向你提出了一个问题/议题，"
            "请你基于专业知识给出结构化、有深度的回答。"
        )
        messages = [
            SystemMessage(content=(agent.system_prompt or "You are a helpful assistant.") + expert_context),
            HumanMessage(content=task_prompt),
        ]

        try:
            content = await run_llm_with_tools(llm, messages, tools)
            expert_responses.append({"agent_name": agent.name, "response": content})
        except Exception as e:
            expert_responses.append({"agent_name": agent.name, "response": f"Error: {e}"})

    # Phase 2: Moderator summarizes
    moderator = db.query(models.Agent).filter(models.Agent.id == moderator_id).first()
    if moderator and expert_responses:
        provider = db.query(models.Provider).filter(
            models.Provider.key == (moderator.provider or "kimi").lower()
        ).first()
        if provider and provider.is_enabled:
            llm = _create_llm_for_agent(moderator, provider)
            tools = get_agent_tools(moderator, override_root_dir=task.file_root_dir or None)
            summary_prompt = _build_moderator_summary_prompt(task_prompt, expert_responses)
            messages = [
                SystemMessage(content=moderator.system_prompt or "You are a helpful assistant."),
                HumanMessage(content=summary_prompt),
            ]
            try:
                content = await run_llm_with_tools(llm, messages, tools)
                return content
            except Exception as e:
                return f"Error in summary: {e}\n\n" + "\n\n".join(
                    [f"{er['agent_name']}: {er['response']}" for er in expert_responses]
                )

    # Fallback: concatenate expert responses
    return "\n\n".join([f"{er['agent_name']}: {er['response']}" for er in expert_responses])


async def _run_task(task_id: int):
    """Run a single task with semaphore-controlled concurrency."""
    async with _semaphore:
        db = SessionLocal()
        try:
            task = db.query(models.Task).filter(models.Task.id == task_id).first()
            if not task:
                return

            # Update status
            task.status = "in_progress"
            task.progress = 0
            db.commit()

            # Simulate progress (0 -> 30 -> 60 -> 90 -> 100)
            progress_steps = [10, 30, 50, 70, 90]
            step_index = 0

            if task.assignee_type == "agent":
                result = await _execute_with_agent(task, db)
            elif task.assignee_type == "group":
                result = await _execute_with_group(task, db)
            else:
                result = "Error: Unknown assignee type"

            task.result = result
            task.status = "completed"
            task.progress = 100
            db.commit()
        except Exception as e:
            task = db.query(models.Task).filter(models.Task.id == task_id).first()
            if task:
                task.result = f"Error: {e}"
                task.status = "completed"
                task.progress = 100
                db.commit()
        finally:
            db.close()
            _executing_tasks.pop(task_id, None)


def submit_task(task_id: int) -> bool:
    """Submit a task for execution. Returns True if submitted, False if already running."""
    if task_id in _executing_tasks and not _executing_tasks[task_id].done():
        return False
    task = asyncio.create_task(_run_task(task_id))
    _executing_tasks[task_id] = task
    return True


def get_task_progress(task_id: int) -> int:
    """Get current execution progress for a task."""
    if task_id not in _executing_tasks:
        return 100  # Not running = done or not started
    task = _executing_tasks[task_id]
    if task.done():
        return 100
    return 50  # Running, return intermediate progress


def set_max_concurrent_tasks(n: int):
    """Update max concurrent tasks limit."""
    global MAX_CONCURRENT_TASKS, _semaphore
    MAX_CONCURRENT_TASKS = max(1, min(20, n))
    _semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)


def get_max_concurrent_tasks() -> int:
    return MAX_CONCURRENT_TASKS


# ---------- Scheduler ----------
_scheduler_task: Optional[asyncio.Task] = None


async def _scheduler_loop():
    """Background scheduler: auto-start pending auto-execute tasks up to concurrency limit."""
    while True:
        await asyncio.sleep(3)
        db = SessionLocal()
        try:
            running_count = sum(1 for t in _executing_tasks.values() if not t.done())
            if running_count >= MAX_CONCURRENT_TASKS:
                continue

            pending_tasks = (
                db.query(models.Task)
                .filter(
                    models.Task.status == "pending",
                    models.Task.auto_execute == True,
                    models.Task.assignee_id.isnot(None),
                )
                .order_by(models.Task.created_at)
                .all()
            )

            for task in pending_tasks:
                if running_count >= MAX_CONCURRENT_TASKS:
                    break
                existing = _executing_tasks.get(task.id)
                if existing and not existing.done():
                    continue
                bg_task = asyncio.create_task(_run_task(task.id))
                _executing_tasks[task.id] = bg_task
                running_count += 1
        finally:
            db.close()


def start_scheduler():
    """Start the background task scheduler."""
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_scheduler_loop())


def stop_scheduler():
    """Stop the background task scheduler."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
