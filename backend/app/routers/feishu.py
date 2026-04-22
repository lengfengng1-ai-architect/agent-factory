"""Feishu bot API (status, connect, disconnect, history)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.feishu_ws import start_feishu_ws, stop_feishu_ws, get_ws_status
from app.redis_client import get_feishu_chat_history

router = APIRouter()


@router.get("/feishu/status/{agent_id}")
def get_feishu_status(agent_id: int):
    """Get Feishu WebSocket connection status for an agent."""
    return get_ws_status(agent_id)


@router.post("/feishu/connect/{agent_id}")
def connect_feishu(agent_id: int, db: Session = Depends(get_db)):
    """Manually start Feishu WebSocket connection for an agent."""
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    success = start_feishu_ws(agent)
    return {"success": success, "agent_id": agent_id}


@router.post("/feishu/disconnect/{agent_id}")
def disconnect_feishu(agent_id: int):
    """Manually stop Feishu WebSocket connection for an agent."""
    stop_feishu_ws(agent_id)
    return {"success": True, "agent_id": agent_id}


@router.get("/feishu/history/{agent_id}")
def get_feishu_history(agent_id: int, db: Session = Depends(get_db)):
    """Get Feishu chat history for an agent."""
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"messages": get_feishu_chat_history(agent_id)}
