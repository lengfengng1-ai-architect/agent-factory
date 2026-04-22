import asyncio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app import models, schemas
from app.task_engine import (
    _run_task, _executing_tasks,
    get_task_progress, get_max_concurrent_tasks, set_max_concurrent_tasks,
)

router = APIRouter()


@router.get("/concurrency")
def get_concurrency_config():
    return {"max_concurrent_tasks": get_max_concurrent_tasks()}


@router.put("/concurrency")
def update_concurrency_config(payload: dict):
    n = payload.get("max_concurrent_tasks", 3)
    set_max_concurrent_tasks(int(n))
    return {"max_concurrent_tasks": get_max_concurrent_tasks()}


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
    return query.all()


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
def breakdown_task(task_id: int, db: Session = Depends(get_db)):
    """Break down a task into workflow steps using LLM."""
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # TODO: Phase 2 中实现真正的 LLM 拆解
    # 这里先返回占位，让 API 可用
    return {
        "task_id": task_id,
        "message": "Breakdown will be implemented in Phase 2",
        "placeholder_steps": []
    }
