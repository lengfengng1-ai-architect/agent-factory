import os
from typing import List, Optional
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_community.agent_toolkits.file_management.toolkit import FileManagementToolkit
from app import models


def get_workspace_path(agent_id: int) -> str:
    """Get the workspace directory path for an agent."""
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
    path = os.path.join(base, str(agent_id))
    os.makedirs(path, exist_ok=True)
    return path


def get_agent_tools(agent: models.Agent, override_root_dir: Optional[str] = None) -> List[BaseTool]:
    """Build tool list for an agent based on its config."""
    tools: List[BaseTool] = []
    cfg = agent.config or {}

    if cfg.get("enable_browsing"):
        tools.append(DuckDuckGoSearchRun())

    if cfg.get("enable_file_access"):
        root = override_root_dir or cfg.get("file_access_root", "")
        if root:
            if not os.path.isabs(root):
                root = os.path.join(os.path.dirname(os.path.dirname(__file__)), root)
        else:
            root = get_workspace_path(agent.id)
        os.makedirs(root, exist_ok=True)
        toolkit = FileManagementToolkit(root_dir=root)
        tools.extend(toolkit.get_tools())

    return tools


async def run_llm_with_tools(llm, messages, tools):
    """Run LLM with tool calling loop (non-streaming). Returns final text content."""
    if not tools:
        response = await llm.ainvoke(messages)
        return response.content

    llm_with_tools = llm.bind_tools(tools)
    response = await llm_with_tools.ainvoke(messages)

    if response.tool_calls:
        messages.append(response)
        for tool_call in response.tool_calls:
            tool = next((t for t in tools if t.name == tool_call["name"]), None)
            if tool:
                try:
                    result = await tool.ainvoke(tool_call["args"])
                except Exception as e:
                    result = f"Error executing tool: {e}"
            else:
                result = f"Tool '{tool_call['name']}' not found"
            messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))
        response = await llm_with_tools.ainvoke(messages)

    return response.content
