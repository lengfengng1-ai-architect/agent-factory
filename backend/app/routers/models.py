from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models

router = APIRouter()

BUILTIN_FALLBACKS = {
    "kimi": [
        {"id": "kimi-latest", "name": "Kimi Latest"},
        {"id": "kimi-k2", "name": "Kimi K2"},
        {"id": "kimi-k1.5", "name": "Kimi K1.5"},
    ],
    "openai": [
        {"id": "gpt-4o", "name": "GPT-4o"},
        {"id": "gpt-4o-mini", "name": "GPT-4o Mini"},
        {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
        {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo"},
    ],
    "deepseek": [
        {"id": "deepseek-chat", "name": "DeepSeek Chat (V3.2)"},
        {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner (V3.2)"},
    ],
}


@router.get("/models")
def list_models(provider: str = "kimi", db: Session = Depends(get_db)):
    db_provider = db.query(models.Provider).filter(models.Provider.key == provider.lower()).first()
    if not db_provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    discovered = db.query(models.ProviderModel).filter(
        models.ProviderModel.provider_id == db_provider.id
    ).all()
    if discovered:
        return {"models": [{"id": m.model_id, "name": m.name} for m in discovered]}

    return {"models": BUILTIN_FALLBACKS.get(provider.lower(), [])}
