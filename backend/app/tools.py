import os
from typing import List
from langchain_core.tools import BaseTool
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.agent_toolkits.file_management.toolkit import FileManagementToolkit
from app import models


def get_workspace_path(agent_id: int) -> str:
    """Get the workspace directory path for an agent."""
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
    path = os.path.join(base, str(agent_id))
    os.makedirs(path, exist_ok=True)
    return path


def get_agent_tools(agent: models.Agent) -> List[BaseTool]:
    """Build tool list for an agent based on its config."""
    tools: List[BaseTool] = []
    cfg = agent.config or {}

    if cfg.get("enable_browsing"):
        tools.append(DuckDuckGoSearchRun())

    if cfg.get("enable_file_access"):
        root = cfg.get("file_access_root", "")
        if root:
            # Use configured root (relative to project root)
            if not os.path.isabs(root):
                root = os.path.join(os.path.dirname(os.path.dirname(__file__)), root)
        else:
            # Default per-agent sandbox
            root = get_workspace_path(agent.id)
        os.makedirs(root, exist_ok=True)
        toolkit = FileManagementToolkit(root_dir=root)
        tools.extend(toolkit.get_tools())

    return tools
