import asyncio
from typing import Optional
from sqlalchemy.orm import Session
from langchain.messages import HumanMessage, SystemMessage
from app.tools import get_agent_tools, run_llm_with_tools
from app.llm_factory import create_llm
from app import models
from app.database import SessionLocal

MAX_CONCURRENT_TASKS = 3
_semaphore: asyncio.Semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
_executing_tasks: dict[int, asyncio.Task] = {}

KIMI_CODE_BASE_URL = "https://api.kimi.com/coding/v1"


async def _execute_with_agent(task: models.Task, db: Session):
    agent = db.query(models.Agent).filter(models.Agent.id == task.assignee_id).first()
    if not agent:
        return "Error: Agent not found"

    provider = db.query(models.Provider).filter(
        models.Provider.key == (agent.provider or "kimi").lower()
    ).first()
    if not provider or not provider.is_enabled:
        return "Error: Provider not available"

    llm = create_llm(agent, provider)
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

        llm = create_llm(agent, provider)
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
            llm = create_llm(moderator, provider)
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


from pydantic import BaseModel, Field

class _WorkflowDecision(BaseModel):
    """Decision on whether a task needs a multi-step workflow."""
    needs_workflow: bool = Field(description="Whether the task requires multi-step workflow execution")
    reasoning: str = Field(description="Brief reasoning for the decision")


async def _should_use_workflow(task: models.Task, db: Session) -> bool:
    """Use LLM with structured output to decide if a task needs multi-step workflow.

    Uses LangChain v1 ProviderStrategy for reliable structured output.
    """
    agent = db.query(models.Agent).filter(models.Agent.id == task.assignee_id).first()
    if not agent:
        return False

    provider = db.query(models.Provider).filter(
        models.Provider.key == (agent.provider or "kimi").lower()
    ).first()
    if not provider or not provider.is_enabled:
        return False

    llm = create_llm(agent, provider)

    prompt = f"""请判断以下任务是否需要拆解为多步骤工作流来执行。

【任务标题】{task.title}
【任务描述】{task.description or "（无）"}

判断标准：
- 如果任务简单明确，可以一次性直接完成（如：简单问答、翻译、写一段短文字、总结等），回答 false
- 如果任务复杂，需要分阶段、多步骤规划执行（如：写文章需要大纲→草稿→润色、开发项目需要调研→设计→编码→测试、复杂分析需要多轮推理等），回答 true"""

    messages = [
        SystemMessage(content="You are a task complexity evaluator."),
        HumanMessage(content=prompt),
    ]

    try:
        # Use provider-native structured output (v1 recommended pattern)
        structured_llm = llm.with_structured_output(_WorkflowDecision)
        result = await structured_llm.ainvoke(messages)
        return result.needs_workflow
    except Exception:
        # Fallback: direct execution on error to avoid blocking
        return False


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

            # Workflow mode
            if task.workflow_plan:
                from app.workflow_engine import execute_workflow
                await execute_workflow(task_id)
                return

            # Auto-decide: simple task = direct execution, complex task = workflow
            if not task.workflow_plan:
                needs_workflow = await _should_use_workflow(task, db)
                if needs_workflow:
                    from app.workflow_engine import breakdown_task as wf_breakdown, execute_workflow
                    try:
                        await wf_breakdown(task, db)
                        db.refresh(task)
                        await execute_workflow(task_id)
                        return
                    except Exception as e:
                        # Fallback to direct execution if breakdown fails
                        task.result = f"Workflow breakdown failed: {e}. Falling back to direct execution.\n\n"
                        db.commit()

            # Legacy single-shot mode
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
    """Background scheduler: auto-start pending tasks and monitor running workflows."""
    while True:
        await asyncio.sleep(3)
        db = SessionLocal()
        try:
            # ── Existing: auto-start pending tasks ──
            running_count = sum(1 for t in _executing_tasks.values() if not t.done())
            if running_count < MAX_CONCURRENT_TASKS:
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

            # ── NEW: Monitor running workflows ──
            await _monitor_workflows(db)

        finally:
            db.close()


async def _monitor_workflows(db: Session):
    """Check running workflows for timeouts and send progress notifications."""
    from datetime import datetime, timezone, timedelta
    from app.workflow_engine import execute_workflow, DEFAULT_TIMEOUT_MINUTES
    from app.feishu_client import send_text_message

    running_tasks = (
        db.query(models.Task)
        .filter(models.Task.workflow_status == "running")
        .all()
    )

    for task in running_tasks:
        # Find currently running step
        running_step = db.query(models.WorkflowStep).filter(
            models.WorkflowStep.task_id == task.id,
            models.WorkflowStep.status == "running"
        ).first()

        if running_step and running_step.started_at:
            timeout = (task.workflow_config or {}).get("timeout_minutes", DEFAULT_TIMEOUT_MINUTES)
            elapsed = datetime.now(timezone.utc) - running_step.started_at
            if elapsed > timedelta(minutes=timeout):
                # Timeout: mark as failed and retry
                running_step.status = "failed"
                running_step.result = f"Timeout after {timeout} minutes"
                db.commit()

                cfg = task.workflow_config or {}
                max_retries = cfg.get("retry_count", 3)
                if running_step.retry_count < max_retries:
                    running_step.retry_count += 1
                    running_step.status = "pending"
                    db.commit()
                    # Resume workflow
                    asyncio.create_task(execute_workflow(task.id))
                else:
                    task.workflow_status = "failed"
                    task.status = "completed"
                    db.commit()
                    _notify_feishu(task, f"❌ 任务「{task.title}」的步骤「{running_step.name}」超时，已达到最大重试次数。", db)

        # Check for waiting_feedback steps and notify
        waiting_step = db.query(models.WorkflowStep).filter(
            models.WorkflowStep.task_id == task.id,
            models.WorkflowStep.status == "waiting_feedback"
        ).first()

        if waiting_step:
            # Only notify if waiting for more than 1 minute (avoid spam)
            if waiting_step.completed_at:
                wait_time = datetime.now(timezone.utc) - waiting_step.completed_at
                if wait_time > timedelta(minutes=1):
                    _notify_feishu(task, f"⏸️ 任务「{task.title}」的步骤「{waiting_step.name}」已完成，等待您的确认。请前往平台查看。", db)


def _notify_feishu(task: models.Task, message: str, db: Session):
    """Send notification via Feishu if the task's agent has Feishu bot configured."""
    if task.assignee_type != "agent" or not task.assignee_id:
        return
    agent = db.query(models.Agent).filter(models.Agent.id == task.assignee_id).first()
    if not agent:
        return
    feishu_cfg = (agent.config or {}).get("feishu", {})
    if not feishu_cfg.get("enabled"):
        return
    app_id = feishu_cfg.get("app_id", "")
    app_secret = feishu_cfg.get("app_secret", "")
    if not app_id or not app_secret:
        return
    try:
        # Send to a default conversation or broadcast
        # For now, we don't have a stored sender_id, so we skip direct message
        # This is a placeholder for future enhancement when sender_id tracking is added
        pass
    except Exception:
        pass


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
