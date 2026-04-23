"""Long-running task workflow engine: breakdown + dependency graph execution.

Uses LangChain v1 structured output (with_structured_output) for reliable
workflow breakdown instead of manual JSON parsing.
"""

import os
import json
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from langchain.messages import HumanMessage, SystemMessage

from app import models
from app.database import SessionLocal
from app.llm_factory import create_llm
from app.tools import get_agent_tools, run_llm_with_tools

MAX_WORKFLOW_STEPS = 50
DEFAULT_TIMEOUT_MINUTES = 30
DEFAULT_RETRY_COUNT = 3


# ── Structured Output Schema ──

class _WorkflowStepSpec(BaseModel):
    """Specification for a single workflow step.

    Flexible schema that accepts multiple field naming conventions
    since LLMs may not strictly follow the schema field names.
    """
    name: str = Field(default="", alias="title", description="步骤名称（简短，20字以内）")
    description: str = Field(default="", alias="desc", description="步骤的具体执行指令（详细 prompt）")
    id: int = Field(default=0, alias="step_id", description="步骤ID（可作为order_index的备选）")
    order_index: int = Field(default=0, alias="index", description="执行顺序（从 0 开始）")
    checkpoint: bool = Field(default=False, description="是否需要用户确认后再继续")
    depends_on: List[int] = Field(default_factory=list, alias="dependencies", description="依赖的前置步骤 order_index 列表（空数组表示无依赖）")
    output_type: str = Field(default="", description='步骤产物类型: "draft" | "analysis" | "review"')

    model_config = {"populate_by_name": True}


class _WorkflowBreakdown(BaseModel):
    """Structured output for task workflow breakdown."""
    product_description: str = Field(default="", description="用一句话描述最终产物的格式和类型")
    steps: List[_WorkflowStepSpec] = Field(default_factory=list, description="步骤数组")


# ── Breakdown ──

async def breakdown_task(task: models.Task, db: Session, require_first_checkpoint: bool = None):
    """Use LLM to break down a task into workflow steps.

    Tries LangChain v1 with_structured_output first for reliable JSON,
    falls back to manual JSON parsing if structured output fails
    (some providers don't fully support schema-constrained generation).
    """
    cfg = task.workflow_config or {}
    if require_first_checkpoint is None:
        require_first_checkpoint = not cfg.get("disable_checkpoints", True)
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
    
    llm = create_llm(agent, provider)
    
    prompt = f"""你是一位任务规划专家。请将以下复杂任务拆解为可执行的步骤列表。

【任务标题】{task.title}
【任务描述】{task.description or ""}

请分析任务类型，推断最终产物的格式（如：文章、代码、报告、设计稿、数据分析结果等），然后输出 JSON 对象，包含两个字段：

1. product_description: 用一句话描述最终产物的格式和类型

2. steps: 步骤数组，每个元素包含：
   - name: 步骤名称（简短，20字以内）
   - description: 步骤的具体执行指令（详细 prompt）
   - order_index: 执行顺序（从 0 开始）
   - checkpoint: 是否需要用户确认后再继续（true/false）
   - depends_on: 依赖的前置步骤 order_index 列表（空数组表示无依赖）
   - output_type: 步骤产物类型，必须是以下之一：
     * "draft" — 该步骤的产物是直接构成最终产物的内容
     * "analysis" — 该步骤的产物是内部分析/规划
     * "review" — 该步骤的产物是审校/检查意见

注意：
1. 步骤数控制在 3-20 个
2. 依赖关系必须形成有向无环图（DAG）
3. 关键里程碑节点应设置为 checkpoint=true
4. 最终产物由所有 output_type=draft 的步骤产物按顺序聚合而成

只输出 JSON，不要其他解释。"""

    messages = [
        SystemMessage(content="You are a task planning expert. Output only valid JSON."),
        HumanMessage(content=prompt),
    ]
    
    # Try structured output first (v1 recommended pattern)
    try:
        structured_llm = llm.with_structured_output(_WorkflowBreakdown)
        result = await structured_llm.ainvoke(messages)
        product_description = result.product_description or "最终产物"
        steps_data = result.steps
    except Exception:
        # Fallback: manual JSON parsing for providers with weak structured output support
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
        
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("LLM did not return a dict with product_description and steps")
        
        product_description = data.get("product_description", "最终产物")
        raw_steps = data.get("steps", [])
        if not isinstance(raw_steps, list):
            raise ValueError("LLM did not return a steps list")
        
        # Normalize step dicts to _WorkflowStepSpec
        steps_data = []
        for i, rs in enumerate(raw_steps):
            if not isinstance(rs, dict):
                continue
            steps_data.append(_WorkflowStepSpec(
                name=rs.get("name") or rs.get("title") or f"步骤 {i+1}",
                description=rs.get("description", rs.get("desc", "")),
                id=rs.get("id", rs.get("step_id", 0)),
                order_index=rs.get("order_index", rs.get("index", rs.get("id", i))),
                checkpoint=bool(rs.get("checkpoint", False)),
                depends_on=rs.get("depends_on", rs.get("dependencies", [])),
                output_type=rs.get("output_type", ""),
            ))
    
    if len(steps_data) > MAX_WORKFLOW_STEPS:
        steps_data = steps_data[:MAX_WORKFLOW_STEPS]
    
    # Create WorkflowStep records
    created_steps = []
    order_to_id = {}
    
    for i, sd in enumerate(steps_data):
        # LLM may return 'id' instead of 'order_index'; use id as fallback
        order_idx = sd.order_index if sd.order_index else (sd.id if sd.id else i)
        step = models.WorkflowStep(
            task_id=task.id,
            name=sd.name or f"步骤 {i+1}",
            description=sd.description or "",
            order_index=order_idx,
            checkpoint=bool(sd.checkpoint),
            output_type=sd.output_type or "",
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
        dep_orders = sd.depends_on or []
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
        "product_description": product_description,
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
    
    llm = create_llm(agent, provider)
    tools = get_agent_tools(agent, override_root_dir=task.file_root_dir or None)
    
    # Collect FULL artifact content from completed dependency steps
    dep_results = []
    if step.depends_on:
        dep_steps = db.query(models.WorkflowStep).filter(
            models.WorkflowStep.id.in_(step.depends_on)
        ).all()
        for ds in dep_steps:
            content = ""
            # Prefer reading full artifact file over truncated result
            if ds.artifact_path and os.path.exists(ds.artifact_path):
                try:
                    with open(ds.artifact_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception:
                    content = ds.result or ""
            else:
                content = ds.result or ""
            if content:
                # Strip the "# Step Name" header we added when saving
                lines = content.split("\n")
                if lines and lines[0].startswith("# "):
                    content = "\n".join(lines[1:]).strip()
                dep_results.append(f"--- {ds.name} ---\n{content[:3000]}")
    
    context = ""
    if dep_results:
        context = "\n\n".join(dep_results) + "\n\n"
    
    cfg = task.workflow_config or {}
    product_description = cfg.get("product_description", "最终产物")
    
    if step.output_type == "draft":
        output_instruction = f"""你的输出必须直接是最终产物的一部分。
【最终产物描述】{product_description}

要求：
1. 输出格式必须与最终产物一致（如：文章正文、代码片段、报告内容等）
2. 不要添加步骤标题、元数据标记（如"【当前步骤执行结果】"）或分析框架说明
3. 不要重复前置步骤已经产出的内容，只写本步骤负责的新内容
4. 保持与前置步骤一致的格式和风格"""
    elif step.output_type == "analysis":
        output_instruction = """你的输出是内部分析/规划结果，用于指导后续步骤。
要求：
1. 输出简洁、有针对性的分析结论或规划要点
2. 可以使用结构化格式（如列表、表格）
3. 不需要写成最终产物的格式"""
    elif step.output_type == "review":
        output_instruction = """你的输出是审校/检查意见。
要求：
1. 指出当前产物中的问题和改进建议
2. 如果发现问题，请说明具体的修改方向
3. 不需要重写全部内容，只给出关键意见"""
    else:
        output_instruction = f"""你的输出应该直接是最终产物的一部分。
【最终产物描述】{product_description}

要求：
1. 输出格式必须与最终产物一致
2. 不要添加步骤标题或元数据标记
3. 不要重复前置步骤已经产出的内容"""
    
    prompt = f"""{context}【当前步骤】{step.name}
【执行指令】{step.description}

{output_instruction}"""

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
        from app.database import workspace_dir
        task_dir = os.path.join(workspace_dir, "tasks", str(task.id))
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
            # Re-read task config each iteration so runtime changes take effect
            db.refresh(task)
            cfg = task.workflow_config or {}
            disable_checkpoints = cfg.get("disable_checkpoints", True)
            max_retries = cfg.get("retry_count", DEFAULT_RETRY_COUNT)
            
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
                    # Aggregate final result from all steps
                    _aggregate_workflow_result(task, all_steps, db)
                    db.commit()
                break
            
            # Execute the first executable step
            step = executable[0]
            await execute_step(step, task, db)
            
            # Refresh step from DB
            db.refresh(step)
            
            if step.status == "failed":
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
            
            # If checkpoint, pause for human feedback (unless globally disabled)
            if step.checkpoint and not disable_checkpoints:
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


def _clean_step_content(content: str) -> str:
    """Remove meta markers and step headers from LLM output."""
    lines = content.split("\n")
    # Remove first line if it's a markdown header we added
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    
    result_lines = []
    skip_patterns = [
        "【当前步骤执行结果】",
        "---",
    ]
    in_skip = False
    for line in lines:
        stripped = line.strip()
        # Skip decorative separator lines
        if stripped == "---" or stripped.startswith("--- ") and stripped.endswith(" ---"):
            continue
        # Skip meta markers
        if any(p in stripped for p in skip_patterns):
            continue
        result_lines.append(line)
    
    return "\n".join(result_lines).strip()


def _aggregate_workflow_result(task: models.Task, steps: list, db: Session):
    """Merge draft-step artifacts into the final product."""
    import os
    
    # Only aggregate steps with output_type="draft" (or empty fallback)
    draft_steps = []
    for step in sorted(steps, key=lambda s: s.order_index):
        if step.status != "completed":
            continue
        if step.output_type == "draft" or not step.output_type:
            draft_steps.append(step)
    
    # Build final product from artifact files (full content, not truncated result)
    parts = []
    for step in draft_steps:
        content = ""
        if step.artifact_path and os.path.exists(step.artifact_path):
            try:
                with open(step.artifact_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                content = step.result or ""
        else:
            content = step.result or ""
        
        cleaned = _clean_step_content(content)
        if cleaned:
            parts.append(cleaned)
    
    # Deduplicate: remove paragraphs that appear in multiple steps
    seen_paragraphs = set()
    deduped_parts = []
    for part in parts:
        paragraphs = part.split("\n\n")
        unique_paras = []
        for para in paragraphs:
            fingerprint = para.strip()[:100]
            if fingerprint and fingerprint not in seen_paragraphs:
                seen_paragraphs.add(fingerprint)
                unique_paras.append(para)
        if unique_paras:
            deduped_parts.append("\n\n".join(unique_paras))
    
    # Assemble final product
    body = "\n\n".join(deduped_parts)
    
    # Build header
    cfg = task.workflow_config or {}
    product_description = cfg.get("product_description", task.title)
    header = f"# {task.title}\n\n"
    if task.description:
        header += f"{task.description}\n\n"
    
    task.result = header + body
    
    # Write final_artifact.md
    from app.database import workspace_dir
    task_dir = os.path.join(workspace_dir, "tasks", str(task.id))
    if os.path.exists(task_dir):
        final_path = os.path.join(task_dir, "final_artifact.md")
        try:
            with open(final_path, "w", encoding="utf-8") as f:
                f.write(task.result)
        except Exception:
            pass
