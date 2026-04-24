from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models, schemas
from app.tools import get_workspace_path
import os

router = APIRouter()


@router.get("/", response_model=List[schemas.AgentResponse])
def list_agents(db: Session = Depends(get_db)):
    return db.query(models.Agent).all()


@router.post("/", response_model=schemas.AgentResponse)
def create_agent(agent: schemas.AgentCreate, db: Session = Depends(get_db)):
    db_agent = models.Agent(**agent.model_dump())
    db.add(db_agent)
    db.commit()
    db.refresh(db_agent)
    return db_agent


@router.get("/{agent_id}", response_model=schemas.AgentResponse)
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.put("/{agent_id}", response_model=schemas.AgentResponse)
def update_agent(agent_id: int, agent: schemas.AgentUpdate, db: Session = Depends(get_db)):
    db_agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    for key, value in agent.model_dump(exclude_unset=True).items():
        setattr(db_agent, key, value)
    db.commit()
    db.refresh(db_agent)
    return db_agent


@router.delete("/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db)):
    db_agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    db.delete(db_agent)
    db.commit()
    return {"message": "Agent deleted"}


@router.get("/{agent_id}/browser/screenshot")
def get_browser_screenshot(agent_id: int, db: Session = Depends(get_db)):
    """Return the latest browser screenshot for an agent."""
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    ws = get_workspace_path(agent_id)
    path = os.path.join(ws, "browser_latest.png")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No screenshot available")
    return FileResponse(path, media_type="image/png")


@router.get("/{agent_id}/browser/state")
async def get_browser_state(agent_id: int, db: Session = Depends(get_db)):
    """Return current browser state (URL, title) for an agent."""
    from app.tools import _read_browser_state
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    ws = get_workspace_path(agent_id)
    screenshot_path = os.path.join(ws, "browser_latest.png")
    state = _read_browser_state(agent_id)
    return {
        "url": state.get("url"),
        "title": state.get("title"),
        "has_screenshot": os.path.exists(screenshot_path),
    }
