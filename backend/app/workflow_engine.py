"""Long-running task workflow engine: breakdown + dependency graph execution."""

import os
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app import models
from app.database import SessionLocal
from app.task_engine import _create_llm_for_agent
from app.tools import get_agent_tools, run_llm_with_tools

MAX_WORKFLOW_STEPS = 50
DEFAULT_TIMEOUT_MINUTES = 30
DEFAULT_RETRY_COUNT = 3


# ── Breakdown ──

async def breakdown_task(task: models.Task, db: Session, require_first_checkpoint: bool = True):
    """Use LLM to break down a task into workflow steps."""
    agent = None
    if task.assignee_type == "agent" and task.assignee_id:
        agent = db.query(models.Agent).filter(models.Agent.id == task.assignee_id).first()
    
    if not agent:
        raise ValueError("Task has no valid assignee agent")
    
    provider = db.query(models.Provider).filter(
        models.Provider.key == (agent.provider or "kimi").lower()
    ).first()
    if not provider or not provider.is_enabled:
        raise ValueError("Agent provider not available")
    
    llm = _create_llm_for_agent(agent, provider)
    
    prompt = f"""你是一位任务规划专家。请将以下复杂任务拆解为可执行的步骤列表。

【任务标题】{task.title}
【任务描述】{task.description or ""}

请输出 JSON 数组，每个元素包含：
- name: 步骤名称（简短，20字以内）
- description: 步骤的具体执行指令（详细 prompt）
- order_index: 执行顺序（从 0 开始）
- checkpoint: 是否需要用户确认后再继续（true/false）
- depends_on: 依赖的前置步骤 order_index 列表（空数组表示无依赖）

注意：
1. 步骤数控制在 3-20 个
2. 依赖关系必须形成有向无环图（DAG）
3. 关键里程碑节点应设置为 checkpoint=true
4. 如果任务涉及信息收集，设置独立的搜索/调研步骤
5. 如果任务涉及内容创作，设置大纲→草稿→润色的递进步骤

只输出 JSON 数组，不要其他解释。"""

    messages = [
        SystemMessage(content="You are a task planning expert. Output only valid JSON."),
        HumanMessage(content=prompt),
    ]
    
    response = await llm.ainvoke(messages)
    content = response.content.strip()
    
    # Extract JSON from markdown code block if present
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    
    steps_data = json.loads(content)
    if not isinstance(steps_data, list):
        raise ValueError("LLM did not return a list")
    
    if len(steps_data) > MAX_WORKFLOW_STEPS:
        steps_data = steps_data[:MAX_WORKFLOW_STEPS]
    
    # Create WorkflowStep records
    created_steps = []
    order_to_id = {}
    
    for i, sd in enumerate(steps_data):
        step = models.WorkflowStep(
            task_id=task.id,
            name=sd.get("name", f"步骤 {i+1}"),
            description=sd.get("description", ""),
            order_index=sd.get("order_index", i),
            checkpoint=bool(sd.get("checkpoint", False)),
            depends_on=[],  # Will update after all steps created
            agent_id=task.assignee_id if task.assignee_type == "agent" else None,
            status="pending",
        )
        db.add(step)
        db.commit()
        db.refresh(step)
        created_steps.append(step)
        order_to_id[step.order_index] = step.id
    
    # Resolve depends_on from order_index to step_id
    for i, sd in enumerate(steps_data):
        dep_orders = sd.get("depends_on", []) or []
        dep_ids = [order_to_id[o] for o in dep_orders if o in order_to_id]
        created_steps[i].depends_on = dep_ids
    
    db.commit()
    
    # Apply first-step checkpoint override
    if not require_first_checkpoint and created_steps:
        first_step = min(created_steps, key=lambda s: s.order_index)
        if first_step.checkpoint:
            first_step.checkpoint = False
            db.commit()
    
    # Update task
    task.workflow_plan = {"steps_count": len(created_steps), "breakdown_at": datetime.now(timezone.utc).isoformat()}
    task.workflow_status = "idle"
    task.workflow_config = {
        "timeout_minutes": DEFAULT_TIMEOUT_MINUTES,
        "retry_count": DEFAULT_RETRY_COUNT,
        "require_first_checkpoint": require_first_checkpoint,
    }
    db.commit()
    
    return created_steps


# ── Execution ──

def _get_next_executable_steps(task_id: int, db: Session) -> list[models.WorkflowStep]:
    """Find all pending steps whose dependencies are all completed."""
    steps = db.query(models.WorkflowStep).filter(
        models.WorkflowStep.task_id == task_id
    ).order_by(models.WorkflowStep.order_index).all()
    
    completed_ids = {s.id for s in steps if s.status in ("completed", "skipped")}
    pending = [s for s in steps if s.status == "pending"]
    
    executable = []
    for step in pending:
        deps = step.depends_on or []
        if all(d in completed_ids for d in deps):
            executable.append(step)
    
    return executable


async def execute_step(step: models.WorkflowStep, task: models.Task, db: Session):
    """Execute a single workflow step using the assigned agent."""
    agent = db.query(models.Agent).filter(models.Agent.id == step.agent_id).first()
    if not agent:
        step.status = "failed"
        step.result = "Error: Agent not found"
        db.commit()
        return
    
    provider = db.query(models.Provider).filter(
        models.Provider.key == (agent.provider or "kimi").lower()
    ).first()
    if not provider or not provider.is_enabled:
        step.status = "failed"
        step.result = "Error: Provider not available"
        db.commit()
        return
    
    llm = _create_llm_for_agent(agent, provider)
    tools = get_agent_tools(agent, override_root_dir=task.file_root_dir or None)
    
    # Collect results from completed dependency steps
    dep_results = []
    if step.depends_on:
        dep_steps = db.query(models.WorkflowStep).filter(
            models.WorkflowStep.id.in_(step.depends_on)
        ).all()
        for ds in dep_steps:
            if ds.result:
                dep_results.append(f"【{ds.name}】\n{ds.result[:500]}")
    
    context = ""
    if dep_results:
        context = "前置步骤结果:\n" + "\n\n".join(dep_results) + "\n\n"
    
    prompt = f"""{context}【当前步骤】{step.name}
【执行指令】{step.description}

请认真执行上述指令。如果有前置步骤结果，请在此基础上继续。"""

    messages = [
        SystemMessage(content=agent.system_prompt or "You are a helpful assistant."),
        HumanMessage(content=prompt),
    ]
    
    step.status = "running"
    step.started_at = datetime.now(timezone.utc)
    db.commit()
    
    try:
        result = await run_llm_with_tools(llm, messages, tools)
        
        # Save artifact to workspace
        task_dir = os.path.join(os.path.dirname(__file__), "workspace", "tasks", str(task.id))
        os.makedirs(task_dir, exist_ok=True)
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in step.name)
        artifact_path = os.path.join(task_dir, f"{step.order_index:02d}_{safe_name}.md")
        with open(artifact_path, "w", encoding="utf-8") as f:
            f.write(f"# {step.name}\n\n")
            f.write(result)
        
        step.result = result[:2000]  # Truncate for DB storage
        step.artifact_path = artifact_path
        step.status = "completed"
        step.completed_at = datetime.now(timezone.utc)
        
    except Exception as e:
        step.result = f"Error: {e}"
        step.status = "failed"
    
    db.commit()


async def execute_workflow(task_id: int):
    """Execute a workflow task: run executable steps until checkpoint or completion."""
    db = SessionLocal()
    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task or not task.workflow_plan:
            return
        
        task.workflow_status = "running"
        db.commit()
        
        while True:
            executable = _get_next_executable_steps(task_id, db)
            if not executable:
                # No more pending steps — check if all done
                all_steps = db.query(models.WorkflowStep).filter(
                    models.WorkflowStep.task_id == task_id
                ).all()
                if all(s.status in ("completed", "skipped") for s in all_steps):
                    task.status = "completed"
                    task.workflow_status = "completed"
                    task.progress = 100
                    db.commit()
                break
            
            # Execute the first executable step
            step = executable[0]
            await execute_step(step, task, db)
            
            # Refresh step from DB
            db.refresh(step)
            
            if step.status == "failed":
                cfg = task.workflow_config or {}
                max_retries = cfg.get("retry_count", DEFAULT_RETRY_COUNT)
                if step.retry_count < max_retries:
                    step.retry_count += 1
                    step.status = "pending"
                    db.commit()
                    continue
                else:
                    # Update progress before failing
                    all_steps = db.query(models.WorkflowStep).filter(
                        models.WorkflowStep.task_id == task_id
                    ).all()
                    completed = sum(1 for s in all_steps if s.status in ("completed", "skipped"))
                    task.progress = int(completed / len(all_steps) * 100) if all_steps else 0
                    task.workflow_status = "failed"
                    task.status = "completed"
                    db.commit()
                    break
            
            # If checkpoint, pause for human feedback
            if step.checkpoint:
                step.status = "waiting_feedback"
                # Update progress before pausing
                all_steps = db.query(models.WorkflowStep).filter(
                    models.WorkflowStep.task_id == task_id
                ).all()
                completed = sum(1 for s in all_steps if s.status in ("completed", "skipped"))
                task.progress = int(completed / len(all_steps) * 100) if all_steps else 0
                task.workflow_status = "waiting_feedback"
                db.commit()
                break
            
            # Update progress
            all_steps = db.query(models.WorkflowStep).filter(
                models.WorkflowStep.task_id == task_id
            ).all()
            completed = sum(1 for s in all_steps if s.status in ("completed", "skipped"))
            task.progress = int(completed / len(all_steps) * 100)
            db.commit()
    
    finally:
        db.close()
