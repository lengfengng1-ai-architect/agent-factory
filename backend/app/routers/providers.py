import requests
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
        "base_url": "https://api.moonshot.ai/v1",
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
        "base_url": "https://api.deepseek.com/v1/",
        "api_key_env": "DEEPSEEK_API_KEY",
        "description": "DeepSeek AI models",
        "doc_url": "https://platform.deepseek.com",
        "is_builtin": True,
        "config": {"discovery_method": "openai", "discovery_endpoint": "/models"},
    },
    {
        "name": "火山方舟",
        "key": "volces",
        "base_url": "https://ark.cn-beijing.volces.com/api/coding/v3",
        "api_key_env": "VOLCES_API_KEY",
        "description": "字节跳动火山方舟大模型平台",
        "doc_url": "https://www.volcengine.com/product/ark",
        "is_builtin": True,
        "config": {"discovery_method": "none"},
    },
    {
        "name": "阿里云百炼",
        "key": "alibaba",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key_env": "DASHSCOPE_API_KEY",
        "description": "阿里云百炼 Qwen 系列模型",
        "doc_url": "https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope",
        "is_builtin": True,
        "config": {"discovery_method": "none"},
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

    data = provider.model_dump(exclude_unset=True)

    if db_provider.is_builtin:
        allowed = {"base_url", "api_key_env", "description", "doc_url", "is_enabled", "config"}
        for key in list(data.keys()):
            if key not in allowed:
                del data[key]

    for key, value in data.items():
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


@router.post("/{provider_id}/reset", response_model=schemas.ProviderResponse)
def reset_provider(provider_id: int, db: Session = Depends(get_db)):
    db_provider = (
        db.query(models.Provider).filter(models.Provider.id == provider_id).first()
    )
    if not db_provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if not db_provider.is_builtin:
        raise HTTPException(status_code=400, detail="Only builtin providers can be reset")

    defaults = next((p for p in BUILTIN_PROVIDERS if p["key"] == db_provider.key), None)
    if not defaults:
        raise HTTPException(status_code=404, detail="Builtin defaults not found")

    for key, value in defaults.items():
        if key != "is_builtin":
            setattr(db_provider, key, value)
    db.commit()
    db.refresh(db_provider)
    return db_provider


def _discover_openai_models(provider: models.Provider, api_key: str) -> List[dict]:
    """Discover models from OpenAI-compatible /models endpoint."""
    url = provider.base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    models_list = []
    for m in data.get("data", []):
        models_list.append({
            "model_id": m.get("id", ""),
            "name": m.get("id", ""),
            "context_window": None,
        })
    return models_list


def _discover_ollama_models(provider: models.Provider) -> List[dict]:
    """Discover models from Ollama /api/tags endpoint."""
    base = provider.base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    url = base.rstrip("/") + "/api/tags"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    models_list = []
    for m in data.get("models", []):
        name = m.get("name", "")
        models_list.append({
            "model_id": name,
            "name": name,
            "context_window": None,
        })
    return models_list


@router.post("/{provider_id}/discover")
def discover_models(provider_id: int, payload: dict = {}, db: Session = Depends(get_db)):
    provider = db.query(models.Provider).filter(models.Provider.id == provider_id).first()
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if not provider.is_enabled:
        raise HTTPException(status_code=400, detail="Provider is disabled")

    method = (provider.config or {}).get("discovery_method", "none")
    if method == "none":
        raise HTTPException(status_code=400, detail="This provider does not support model discovery")

    api_key = payload.get("api_key", "")
    try:
        if method == "openai":
            discovered = _discover_openai_models(provider, api_key)
        elif method == "ollama":
            discovered = _discover_ollama_models(provider)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown discovery method: {method}")
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to discover models: {str(e)}")

    db.query(models.ProviderModel).filter(models.ProviderModel.provider_id == provider_id).delete()
    for m in discovered:
        db.add(models.ProviderModel(provider_id=provider_id, **m))
    db.commit()

    return {"discovered": len(discovered), "models": discovered}


@router.get("/{provider_id}/models", response_model=List[schemas.ProviderModelResponse])
def list_provider_models(provider_id: int, db: Session = Depends(get_db)):
    return db.query(models.ProviderModel).filter(
        models.ProviderModel.provider_id == provider_id
    ).order_by(models.ProviderModel.name).all()
