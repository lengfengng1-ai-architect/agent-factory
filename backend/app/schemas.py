from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


class AgentBase(BaseModel):
    name: str
    description: Optional[str] = ""
    avatar: Optional[str] = ""
    config: Optional[Dict[str, Any]] = {}
    system_prompt: Optional[str] = "You are a helpful assistant."
    provider: Optional[str] = "kimi"
    model: Optional[str] = "kimi-latest"
    api_url: Optional[str] = "https://api.kimi.com/coding/"
    api_key: Optional[str] = ""


class AgentCreate(AgentBase):
    pass


class AgentUpdate(AgentBase):
    name: Optional[str] = None


class AgentResponse(AgentBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class GroupBase(BaseModel):
    name: str
    description: Optional[str] = ""
    chat_type: Optional[str] = "parallel"
    agent_ids: Optional[List[int]] = []


class GroupCreate(GroupBase):
    pass


class GroupUpdate(GroupBase):
    name: Optional[str] = None
    chat_type: Optional[str] = None


class GroupResponse(GroupBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class TaskBase(BaseModel):
    title: str
    description: Optional[str] = ""
    status: Optional[str] = "pending"
    assignee_type: Optional[str] = "agent"
    assignee_id: int


class TaskCreate(TaskBase):
    pass


class TaskUpdate(TaskBase):
    title: Optional[str] = None
    status: Optional[str] = None


class TaskResponse(TaskBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProviderBase(BaseModel):
    name: str
    key: str
    base_url: str
    api_key_env: Optional[str] = ""
    description: Optional[str] = ""
    doc_url: Optional[str] = ""
    is_enabled: Optional[bool] = True
    config: Optional[Dict[str, Any]] = {}


class ProviderCreate(ProviderBase):
    pass


class ProviderUpdate(ProviderBase):
    name: Optional[str] = None
    key: Optional[str] = None
    base_url: Optional[str] = None


class ProviderResponse(ProviderBase):
    id: int
    is_builtin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ProviderModelBase(BaseModel):
    provider_id: int
    model_id: str
    name: str
    context_window: Optional[int] = None


class ProviderModelResponse(ProviderModelBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
