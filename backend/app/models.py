from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, Boolean
from sqlalchemy.sql import func
from app.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    avatar = Column(String, default="")
    config = Column(JSON, default=dict)
    system_prompt = Column(Text, default="You are a helpful assistant.")
    provider = Column(String, default="kimi")
    model = Column(String, default="kimi-latest")
    api_url = Column(String, default="https://api.kimi.com/coding/")
    api_key = Column(String, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, default="")
    chat_type = Column(String, default="parallel")
    agent_ids = Column(JSON, default=list)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    status = Column(String, default="pending")
    assignee_type = Column(String, default="agent")
    assignee_id = Column(Integer, nullable=True)
    result = Column(Text, default="")
    auto_execute = Column(Boolean, default=False)
    progress = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Provider(Base):
    __tablename__ = "providers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    key = Column(String, unique=True, nullable=False, index=True)
    base_url = Column(String, nullable=False)
    api_key_env = Column(String, default="")
    description = Column(Text, default="")
    doc_url = Column(String, default="")
    is_builtin = Column(Boolean, default=False)
    is_enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ProviderModel(Base):
    __tablename__ = "provider_models"

    id = Column(Integer, primary_key=True, index=True)
    provider_id = Column(Integer, nullable=False, index=True)
    model_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    context_window = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FileSummary(Base):
    __tablename__ = "file_summaries"

    id = Column(Integer, primary_key=True)
    content_hash = Column(String, unique=True, index=True)
    file_name = Column(String, nullable=False)
    file_ext = Column(String)
    file_size = Column(Integer)
    char_count = Column(Integer)
    summary = Column(Text, nullable=False)
    summary_char_count = Column(Integer)
    agent_id = Column(Integer, nullable=True, index=True)
    group_id = Column(Integer, nullable=True, index=True)
    model_id = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
