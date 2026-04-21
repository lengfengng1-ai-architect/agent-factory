from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
import json

router = APIRouter()


@router.post("/{agent_id}/chat")
def chat_with_agent(agent_id: int, payload: dict, db: Session = Depends(get_db)):
    agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    user_message = payload.get("message", "")
    if not user_message:
        raise HTTPException(status_code=400, detail="message is required")

    api_key = agent.api_key or ""
    base_url = agent.api_url or "https://api.kimi.com/coding/"
    model = agent.model or "kimi-latest"
    system_prompt = agent.system_prompt or "You are a helpful assistant."

    if not api_key:
        raise HTTPException(status_code=400, detail="Agent api_key not configured")

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
