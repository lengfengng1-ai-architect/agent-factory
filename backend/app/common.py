"""Common helpers used across routers and engines.

Eliminates repetitive patterns like:
- provider lookup + validation
- LLM instantiation
- agent + provider + tools bundle creation
"""

from typing import Optional, Tuple, List
from sqlalchemy.orm import Session
from langchain.chat_models import init_chat_model
from langchain_core.tools import BaseTool

from app import models
from app.llm_factory import create_llm
from app.tools import get_agent_tools


def get_agent_provider(
    db: Session, agent: models.Agent
) -> models.Provider:
    """Look up and validate the provider for an agent.

    Raises ValueError with a descriptive message if the provider is missing
    or disabled.
    """
    provider = (
        db.query(models.Provider)
        .filter(models.Provider.key == (agent.provider or "kimi").lower())
        .first()
    )
    if not provider:
        raise ValueError(f"Unknown provider: {agent.provider}")
    if not provider.is_enabled:
        raise ValueError(f"Provider {provider.name} is disabled")
    return provider


def get_agent_llm(
    db: Session,
    agent: models.Agent,
    streaming: bool = False,
) -> init_chat_model:
    """Create an LLM instance for an agent with full validation."""
    provider = get_agent_provider(db, agent)
    return create_llm(agent, provider, streaming=streaming)


def get_agent_bundle(
    db: Session,
    agent: models.Agent,
    streaming: bool = False,
    override_root_dir: Optional[str] = None,
) -> Tuple[init_chat_model, List[BaseTool]]:
    """Return (llm, tools) for an agent in one call.

    This is the most common pattern across chat, task, and workflow code.
    """
    provider = get_agent_provider(db, agent)
    llm = create_llm(agent, provider, streaming=streaming)
    tools = get_agent_tools(agent, override_root_dir=override_root_dir)
    return llm, tools


def get_task_assignee_agent(
    db: Session, task: models.Task
) -> models.Agent:
    """Resolve the agent assigned to a task.

    Raises ValueError if the task has no valid agent assignee.
    """
    if task.assignee_type != "agent" or not task.assignee_id:
        raise ValueError("Task has no agent assignee")
    agent = db.query(models.Agent).filter(models.Agent.id == task.assignee_id).first()
    if not agent:
        raise ValueError("Assigned agent not found")
    return agent
