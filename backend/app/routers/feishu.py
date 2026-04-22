"""Feishu bot webhook receiver."""

import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.feishu_client import send_text_message
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

router = APIRouter()


def _resolve_llm_config(agent: models.Agent, db: Session):
    """Resolve base_url, model, api_key for an agent (same logic as chat.py)."""
    provider = db.query(models.Provider).filter(
        models.Provider.key == (agent.provider or "kimi").lower()
    ).first()
    if not provider or not provider.is_enabled:
        raise HTTPException(status_code=400, detail="Provider not available")
    
    base_url = provider.base_url
    model = agent.model or ""
    api_key = agent.api_key or ""
    
    if provider.key == "custom":
        base_url = agent.api_url or base_url
    if provider.key == "ollama":
        api_key = api_key or "ollama"
    
    return base_url, model, api_key


@router.post("/feishu/webhook/{agent_id}")
async def feishu_webhook(agent_id: int, payload: dict, db: Session = Depends(get_db)):
    """Receive Feishu message events and forward to Agent LLM."""
    
    # 1. Find agent
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    
    # 2. Check Feishu config
    feishu_cfg = (agent.config or {}).get("feishu", {})
    if not feishu_cfg.get("enabled"):
        return {"message": "Feishu bot not enabled for this agent"}
    
    app_id = feishu_cfg.get("app_id", "")
    app_secret = feishu_cfg.get("app_secret", "")
    if not app_id or not app_secret:
        return {"message": "Feishu app_id or app_secret not configured"}
    
    # 3. Parse Feishu event
    header = payload.get("header", {})
    event_type = header.get("event_type", "")
    
    if event_type != "im.message.receive_v1":
        return {"message": "ignored"}
    
    event = payload.get("event", {})
    message = event.get("message", {})
    msg_type = message.get("message_type", "")
    
    if msg_type != "text":
        return {"message": "unsupported message type"}
    
    content = json.loads(message.get("content", "{}"))
    text = content.get("text", "").strip()
    
    if not text:
        return {"message": "empty message"}
    
    # Extract sender open_id for reply
    sender_id = event.get("sender", {}).get("sender_id", {}).get("open_id", "")
    if not sender_id:
        return {"message": "no sender"}
    
    # 4. Call Agent LLM
    try:
        base_url, model, api_key = _resolve_llm_config(agent, db)
        
        system_prompt = agent.system_prompt or "You are a helpful assistant."
        
        llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            streaming=False,
            max_tokens=2000,
        )
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"【飞书消息】{text}"),
        ]
        
        response = await llm.ainvoke(messages)
        reply = response.content.strip()
        
    except Exception as e:
        reply = f"抱歉，处理消息时出错：{e}"
    
    # 5. Send reply back to Feishu
    try:
        result = send_text_message(app_id, app_secret, sender_id, reply)
        return {"message": "ok", "feishu_result": result}
    except Exception as e:
        return {"message": "reply failed", "error": str(e)}
