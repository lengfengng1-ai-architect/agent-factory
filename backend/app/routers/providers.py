from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app import models, schemas

router = APIRouter()

BUILTIN_PROVIDERS = [
    {
        "name": "Kimi",
        "key": "kimi",
        "base_url": "https://api.kimi.com/coding/",
        "api_key_env": "KIMI_API_KEY",
        "description": "Moonshot AI Kimi coding models",
        "doc_url": "https://platform.kimi.ai",
        "is_builtin": True,
        "config": {"discovery_method": "none"},
    },
    {
        "name": "OpenAI",
        "key": "openai",
        "base_url": "https://api.openai.com/v1/",
        "api_key_env": "OPENAI_API_KEY",
        "description": "OpenAI GPT models",
        "doc_url": "https://platform.openai.com",
        "is_builtin": True,
        "config": {"discovery_method": "openai", "discovery_endpoint": "/models"},
    },
    {
        "name": "Ollama",
        "key": "ollama",
        "base_url": "http://localhost:11434/v1/",
        "api_key_env": "",
        "description": "Local open-source models via Ollama",
        "doc_url": "https://ollama.com",
        "is_builtin": True,
        "config": {"discovery_method": "ollama", "discovery_endpoint": "/api/tags"},
    },
    {
        "name": "DeepSeek",
        "key": "deepseek",
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
        "description": "DeepSeek AI models",
        "doc_url": "https://platform.deepseek.com",
        "is_builtin": True,
        "config": {"discovery_method": "openai", "discovery_endpoint": "/models"},
    },
    {
        "name": "Custom",
        "key": "custom",
        "base_url": "",
        "api_key_env": "",
        "description": "Custom OpenAI-compatible endpoint",
        "doc_url": "",
        "is_builtin": True,
        "config": {"discovery_method": "none"},
    },
]


def init_builtin_providers(db: Session):
    for data in BUILTIN_PROVIDERS:
        existing = (
            db.query(models.Provider)
            .filter(models.Provider.key == data["key"])
            .first()
        )
        if not existing:
            provider = models.Provider(**data)
            db.add(provider)
    db.commit()


@router.get("/", response_model=List[schemas.ProviderResponse])
def list_providers(db: Session = Depends(get_db)):
    return db.query(models.Provider).all()


@router.post("/", response_model=schemas.ProviderResponse)
def create_provider(provider: schemas.ProviderCreate, db: Session = Depends(get_db)):
    db_provider = models.Provider(**provider.model_dump())
    db.add(db_provider)
    db.commit()
    db.refresh(db_provider)
    return db_provider


@router.get("/{provider_id}", response_model=schemas.ProviderResponse)
def get_provider(provider_id: int, db: Session = Depends(get_db)):
    provider = (
        db.query(models.Provider).filter(models.Provider.id == provider_id).first()
    )
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


@router.put("/{provider_id}", response_model=schemas.ProviderResponse)
def update_provider(
    provider_id: int, provider: schemas.ProviderUpdate, db: Session = Depends(get_db)
):
    db_provider = (
        db.query(models.Provider).filter(models.Provider.id == provider_id).first()
    )
    if not db_provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if db_provider.is_builtin:
        raise HTTPException(status_code=403, detail="Builtin providers cannot be edited")
    for key, value in provider.model_dump(exclude_unset=True).items():
        setattr(db_provider, key, value)
    db.commit()
    db.refresh(db_provider)
    return db_provider


@router.delete("/{provider_id}")
def delete_provider(provider_id: int, db: Session = Depends(get_db)):
    db_provider = (
        db.query(models.Provider).filter(models.Provider.id == provider_id).first()
    )
    if not db_provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if db_provider.is_builtin:
        raise HTTPException(
            status_code=403, detail="Builtin providers cannot be deleted"
        )
    db.delete(db_provider)
    db.commit()
    return {"message": "Provider deleted"}
