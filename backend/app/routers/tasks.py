import asyncio
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app import models, schemas
from app.task_engine import (
    _run_task, _executing_tasks,
    get_task_progress, get_max_concurrent_tasks, set_max_concurrent_tasks,
)
from app.workflow_engine import breakdown_task as wf_breakdown, execute_workflow

router = APIRouter()


@router.get("/concurrency")
def get_concurrency_config():
    return {"max_concurrent_tasks": get_max_concurrent_tasks()}


@router.put("/concurrency")
def update_concurrency_config(payload: dict):
    n = payload.get("max_concurrent_tasks", 3)
    set_max_concurrent_tasks(int(n))
    return {"max_concurrent_tasks": get_max_concurrent_tasks()}


def _enrich_task_workflow_stats(task: models.Task, db: Session):
    """Attach total_steps and completed_steps to a Task for workflow display."""
    if task.workflow_plan:
        steps = db.query(models.WorkflowStep).filter(models.WorkflowStep.task_id == task.id).all()
        task.total_steps = len(steps)
        task.completed_steps = sum(1 for s in steps if s.status in ("completed", "skipped"))
    else:
        task.total_steps = None
        task.completed_steps = None
    return task


@router.get("/", response_model=List[schemas.TaskResponse])
def list_tasks(
    status: Optional[str] = None,
    assignee_type: Optional[str] = None,
    assignee_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    query = db.query(models.Task)
    if status:
        query = query.filter(models.Task.status == status)
    if assignee_type:
        query = query.filter(models.Task.assignee_type == assignee_type)
    if assignee_id is not None:
        query = query.filter(models.Task.assignee_id == assignee_id)
    tasks = query.all()
    for task in tasks:
        _enrich_task_workflow_stats(task, db)
    return tasks


@router.post("/", response_model=schemas.TaskResponse)
def create_task(task: schemas.TaskCreate, db: Session = Depends(get_db)):
    db_task = models.Task(**task.model_dump())
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


@router.get("/{task_id}", response_model=schemas.TaskResponse)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    _enrich_task_workflow_stats(task, db)
    return task


@router.put("/{task_id}", response_model=schemas.TaskResponse)
def update_task(task_id: int, task: schemas.TaskUpdate, db: Session = Depends(get_db)):
    db_task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    for key, value in task.model_dump(exclude_unset=True).items():
        setattr(db_task, key, value)
    db.commit()
    db.refresh(db_task)
    return db_task


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db)):
    db_task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(db_task)
    db.commit()
    return {"message": "Task deleted"}


@router.post("/{task_id}/execute")
async def execute_task(task_id: int, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if not task.assignee_id:
        raise HTTPException(status_code=400, detail="Task has no assignee")

    # Check if already running
    existing = _executing_tasks.get(task_id)
    if existing and not existing.done():
        raise HTTPException(status_code=409, detail="Task is already executing")

    # Start background task in the event loop
    bg_task = asyncio.create_task(_run_task(task_id))
    _executing_tasks[task_id] = bg_task
    return {"message": "Task submitted for execution", "task_id": task_id}


@router.get("/{task_id}/status")
def get_task_status(task_id: int, db: Session = Depends(get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    progress = get_task_progress(task_id)
    if task.status == "in_progress" and progress == 100:
        progress = task.progress or 50
    return {
        "task_id": task_id,
        "status": task.status,
        "progress": progress,
        "result": task.result,
    }


# ── Workflow Steps ──

@router.get("/{task_id}/steps", response_model=List[schemas.WorkflowStepResponse])
def list_task_steps(task_id: int, db: Session = Depends(get_db)):
    return db.query(models.WorkflowStep).filter(models.WorkflowStep.task_id == task_id).order_by(models.WorkflowStep.order_index).all()


@router.post("/{task_id}/steps", response_model=schemas.WorkflowStepResponse)
def create_task_step(task_id: int, step: schemas.WorkflowStepCreate, db: Session = Depends(get_db)):
    db_step = models.WorkflowStep(**step.model_dump())
    db.add(db_step)
    db.commit()
    db.refresh(db_step)
    return db_step


@router.put("/{task_id}/steps/{step_id}", response_model=schemas.WorkflowStepResponse)
def update_task_step(task_id: int, step_id: int, step: schemas.WorkflowStepUpdate, db: Session = Depends(get_db)):
    db_step = db.query(models.WorkflowStep).filter(
        models.WorkflowStep.id == step_id,
        models.WorkflowStep.task_id == task_id
    ).first()
    if not db_step:
        raise HTTPException(status_code=404, detail="Step not found")
    for key, value in step.model_dump(exclude_unset=True).items():
        setattr(db_step, key, value)
    db.commit()
    db.refresh(db_step)
    return db_step


@router.delete("/{task_id}/steps/{step_id}")
def delete_task_step(task_id: int, step_id: int, db: Session = Depends(get_db)):
    db_step = db.query(models.WorkflowStep).filter(
        models.WorkflowStep.id == step_id,
        models.WorkflowStep.task_id == task_id
    ).first()
    if not db_step:
        raise HTTPException(status_code=404, detail="Step not found")
    db.delete(db_step)
    db.commit()
    return {"message": "Step deleted"}


# ── Task Breakdown ──

@router.post("/{task_id}/breakdown")
async def breakdown_task(task_id: int, db: Session = Depends(get_db)):
    """Break down a task into workflow steps using LLM."""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    steps = await wf_breakdown(task, db)
    return {
        "task_id": task_id,
        "steps_count": len(steps),
        "steps": [{"id": s.id, "name": s.name, "order_index": s.order_index, "checkpoint": s.checkpoint} for s in steps]
    }


@router.post("/{task_id}/steps/{step_id}/confirm")
def confirm_step(task_id: int, step_id: int, db: Session = Depends(get_db)):
    """User confirms a checkpoint step and continues workflow execution."""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    step = db.query(models.WorkflowStep).filter(
        models.WorkflowStep.id == step_id,
        models.WorkflowStep.task_id == task_id
    ).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    if step.status != "waiting_feedback":
        raise HTTPException(status_code=400, detail="Step is not waiting for feedback")
    
    # Mark step as completed and continue workflow
    step.status = "completed"
    step.completed_at = datetime.now(timezone.utc)
    db.commit()
    
    # Resume workflow execution in background
    asyncio.create_task(execute_workflow(task_id))
    
    return {"success": True, "message": "Step confirmed, workflow resumed"}


@router.post("/{task_id}/steps/{step_id}/reject")
def reject_step(task_id: int, step_id: int, payload: dict, db: Session = Depends(get_db)):
    """User rejects a checkpoint step result, requiring revision."""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    step = db.query(models.WorkflowStep).filter(
        models.WorkflowStep.id == step_id,
        models.WorkflowStep.task_id == task_id
    ).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    if step.status != "waiting_feedback":
        raise HTTPException(status_code=400, detail="Step is not waiting for feedback")
    
    feedback = payload.get("feedback", "")
    step.status = "pending"
    # Append feedback to description for next execution
    if feedback:
        step.description += f"\n\n【用户反馈】{feedback}"
    db.commit()
    
    return {"success": True, "message": "Step rejected, will be retried with feedback"}


@router.post("/{task_id}/steps/{step_id}/retry")
def retry_step(task_id: int, step_id: int, db: Session = Depends(get_db)):
    """Retry a failed or rejected step."""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    step = db.query(models.WorkflowStep).filter(
        models.WorkflowStep.id == step_id,
        models.WorkflowStep.task_id == task_id
    ).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    
    if step.status not in ("failed", "waiting_feedback"):
        raise HTTPException(status_code=400, detail="Step cannot be retried")
    
    step.status = "pending"
    step.retry_count += 1
    db.commit()
    
    # Resume workflow
    asyncio.create_task(execute_workflow(task_id))
    
    return {"success": True, "message": "Step retry initiated"}


@router.post("/{task_id}/steps/{step_id}/skip")
def skip_step(task_id: int, step_id: int, db: Session = Depends(get_db)):
    """Skip a pending or waiting_feedback step."""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    step = db.query(models.WorkflowStep).filter(
        models.WorkflowStep.id == step_id,
        models.WorkflowStep.task_id == task_id
    ).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    
    step.status = "skipped"
    step.completed_at = datetime.now(timezone.utc)
    db.commit()
    
    # Resume workflow
    asyncio.create_task(execute_workflow(task_id))
    
    return {"success": True, "message": "Step skipped, workflow resumed"}


@router.get("/{task_id}/workflow/progress")
def get_workflow_progress(task_id: int, db: Session = Depends(get_db)):
    """Get workflow execution progress for a task."""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    steps = db.query(models.WorkflowStep).filter(
        models.WorkflowStep.task_id == task_id
    ).order_by(models.WorkflowStep.order_index).all()
    
    total = len(steps)
    completed = sum(1 for s in steps if s.status in ("completed", "skipped"))
    waiting = sum(1 for s in steps if s.status == "waiting_feedback")
    failed = sum(1 for s in steps if s.status == "failed")
    running = sum(1 for s in steps if s.status == "running")
    
    return {
        "task_id": task_id,
        "workflow_status": task.workflow_status,
        "progress": task.progress,
        "total_steps": total,
        "completed_steps": completed,
        "waiting_steps": waiting,
        "failed_steps": failed,
        "running_steps": running,
        "steps": [
            {
                "id": s.id,
                "name": s.name,
                "status": s.status,
                "order_index": s.order_index,
                "checkpoint": s.checkpoint,
                "retry_count": s.retry_count,
                "artifact_path": s.artifact_path,
            }
            for s in steps
        ]
    }
