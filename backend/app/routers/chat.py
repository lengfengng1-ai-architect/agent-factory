from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import json

router = APIRouter()

PROVIDER_CONFIG = {
    "kimi": {
        "base_url": "https://api.kimi.com/coding/",
        "default_model": "kimi-latest",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1/",
        "default_model": "llama3",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1/",
        "default_model": "gpt-4o",
    },
}


@router.post("/{agent_id}/chat")
def chat_with_agent(agent_id: int, payload: dict, db: Session = Depends(get_db)):
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    user_message = payload.get("message", "")
    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")

    provider = (agent.provider or "kimi").lower()
    system_prompt = agent.system_prompt or "You are a helpful assistant."

    if provider == "custom":
        base_url = agent.api_url
        model = agent.model
        api_key = agent.api_key or ""
        if not api_key:
            raise HTTPException(status_code=400, detail="Agent api_key not configured")
    elif provider == "ollama":
        base_url = PROVIDER_CONFIG["ollama"]["base_url"]
        model = agent.model or PROVIDER_CONFIG["ollama"]["default_model"]
        api_key = agent.api_key or "ollama"
    elif provider in PROVIDER_CONFIG:
        base_url = PROVIDER_CONFIG[provider]["base_url"]
        model = agent.model or PROVIDER_CONFIG[provider]["default_model"]
        api_key = agent.api_key or ""
        if not api_key:
            raise HTTPException(status_code=400, detail="Agent api_key not configured")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        streaming=True,
    )

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_message)]

    async def stream():
        async for chunk in llm.astream(messages):
            text = chunk.content
            if text:
                yield f"data: {json.dumps({'content': text}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
