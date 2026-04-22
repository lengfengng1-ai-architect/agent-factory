import os
import shutil
from typing import List, Optional
from langchain.tools import tool, BaseTool
from langchain.messages import ToolMessage
from ddgs import DDGS
from app import models


def get_workspace_path(agent_id: int) -> str:
    """Get the workspace directory path for an agent."""
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "workspace")
    path = os.path.join(base, str(agent_id))
    os.makedirs(path, exist_ok=True)
    return path


@tool
def web_search(query: str) -> str:
    """Search the web for information using DuckDuckGo.

    Use this tool when you need to find up-to-date information,
    research topics, or verify facts from the internet.

    Args:
        query: The search query string.
    """
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            if not results:
                return "No results found."
            return "\n\n".join(
                [
                    f"Title: {r['title']}\nSnippet: {r['body']}\nURL: {r.get('href', 'N/A')}"
                    for r in results
                ]
            )
    except Exception as e:
        return f"Search error: {e}"


def _resolve_path(file_path: str, root_dir: str) -> str:
    """Resolve a path relative to root_dir and enforce sandboxing."""
    full_path = os.path.join(root_dir, file_path)
    real_path = os.path.realpath(full_path)
    real_root = os.path.realpath(root_dir)
    if not real_path.startswith(real_root):
        raise ValueError("Access denied: path is outside the allowed directory.")
    return real_path


def _create_file_tools(root_dir: str) -> List[BaseTool]:
    """Create file management tools scoped to root_dir."""

    @tool
    def read_file(file_path: str) -> str:
        """Read the contents of a file.

        Args:
            file_path: Path to the file relative to the workspace root.
        """
        try:
            real_path = _resolve_path(file_path, root_dir)
            with open(real_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {e}"

    @tool
    def write_file(file_path: str, content: str) -> str:
        """Write content to a file.

        Args:
            file_path: Path to the file relative to the workspace root.
            content: The content to write.
        """
        try:
            real_path = _resolve_path(file_path, root_dir)
            os.makedirs(os.path.dirname(real_path), exist_ok=True)
            with open(real_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"File written successfully: {file_path}"
        except Exception as e:
            return f"Error writing file: {e}"

    @tool
    def list_directory(directory: str = ".") -> str:
        """List files and directories in a specified folder.

        Args:
            directory: Directory path relative to the workspace root.
        """
        try:
            real_path = _resolve_path(directory, root_dir)
            items = os.listdir(real_path)
            return "\n".join(items) if items else "(empty directory)"
        except Exception as e:
            return f"Error listing directory: {e}"

    @tool
    def copy_file(source_path: str, destination_path: str) -> str:
        """Create a copy of a file in a specified location.

        Args:
            source_path: Source file path relative to the workspace root.
            destination_path: Destination file path relative to the workspace root.
        """
        try:
            real_src = _resolve_path(source_path, root_dir)
            real_dst = _resolve_path(destination_path, root_dir)
            os.makedirs(os.path.dirname(real_dst), exist_ok=True)
            shutil.copy2(real_src, real_dst)
            return f"File copied from {source_path} to {destination_path}"
        except Exception as e:
            return f"Error copying file: {e}"

    @tool
    def move_file(source_path: str, destination_path: str) -> str:
        """Move or rename a file from one location to another.

        Args:
            source_path: Source file path relative to the workspace root.
            destination_path: Destination file path relative to the workspace root.
        """
        try:
            real_src = _resolve_path(source_path, root_dir)
            real_dst = _resolve_path(destination_path, root_dir)
            os.makedirs(os.path.dirname(real_dst), exist_ok=True)
            shutil.move(real_src, real_dst)
            return f"File moved from {source_path} to {destination_path}"
        except Exception as e:
            return f"Error moving file: {e}"

    @tool
    def file_delete(file_path: str) -> str:
        """Delete a file.

        Args:
            file_path: Path to the file relative to the workspace root.
        """
        try:
            real_path = _resolve_path(file_path, root_dir)
            os.remove(real_path)
            return f"File deleted: {file_path}"
        except Exception as e:
            return f"Error deleting file: {e}"

    @tool
    def file_search(pattern: str, directory: str = ".") -> str:
        """Recursively search for files matching a regex pattern.

        Args:
            pattern: Regex pattern to match filenames.
            directory: Directory to search in, relative to the workspace root.
        """
        import re

        try:
            real_path = _resolve_path(directory, root_dir)
            matches = []
            for root, _, files in os.walk(real_path):
                for f in files:
                    if re.search(pattern, f):
                        rel = os.path.relpath(os.path.join(root, f), real_path)
                        matches.append(rel)
            return "\n".join(matches) if matches else "No matches found."
        except Exception as e:
            return f"Error searching files: {e}"

    return [
        read_file,
        write_file,
        list_directory,
        copy_file,
        move_file,
        file_delete,
        file_search,
    ]


def get_agent_tools(
    agent: models.Agent, override_root_dir: Optional[str] = None
) -> List[BaseTool]:
    """Build tool list for an agent based on its config."""
    tools: List[BaseTool] = []
    cfg = agent.config or {}

    if cfg.get("enable_browsing"):
        tools.append(web_search)

    if cfg.get("enable_file_access"):
        root = override_root_dir or cfg.get("file_access_root", "")
        if root:
            if not os.path.isabs(root):
                root = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)), root
                )
        else:
            root = get_workspace_path(agent.id)
        os.makedirs(root, exist_ok=True)
        tools.extend(_create_file_tools(root))

    return tools


async def run_llm_with_tools(llm, messages, tools, system_prompt=None, middleware=None):
    """Run LLM with tool calling loop (non-streaming). Returns final text content.

    Uses langchain.agents.create_agent for 1.x recommended agent execution.
    Supports optional middleware for error handling, summarization, etc.
    """
    if not tools:
        if system_prompt:
            messages = [SystemMessage(content=system_prompt)] + messages
        response = await llm.ainvoke(messages)
        return response.content

    from langchain.agents import create_agent

    kwargs = {}
    if system_prompt:
        kwargs["system_prompt"] = system_prompt
    if middleware:
        kwargs["middleware"] = middleware

    agent = create_agent(llm, tools=tools, **kwargs)
    result = await agent.ainvoke({"messages": messages})
    last_msg = result["messages"][-1]
    return last_msg.content


def get_agent_middleware(agent: models.Agent):
    """Build middleware list for an agent based on its config.

    Supported middleware:
    - ToolCallLimitMiddleware: limit tool calls per run/thread
    - SummarizationMiddleware: auto-summarize when context window fills
    """
    from langchain.agents.middleware import (
        ToolCallLimitMiddleware,
        SummarizationMiddleware,
    )

    cfg = agent.config or {}
    middleware = []

    # Tool call limits
    tool_limits = cfg.get("tool_call_limits")
    if tool_limits:
        if isinstance(tool_limits, dict):
            # Per-tool limits
            for tool_name, limits in tool_limits.items():
                middleware.append(ToolCallLimitMiddleware(
                    tool_name=tool_name,
                    run_limit=limits.get("run_limit"),
                    thread_limit=limits.get("thread_limit"),
                ))
        elif isinstance(tool_limits, int):
            # Global limit
            middleware.append(ToolCallLimitMiddleware(run_limit=tool_limits))

    # Summarization
    summarization = cfg.get("summarization")
    if summarization:
        summary_model = summarization.get("model", agent.model)
        trigger = summarization.get("trigger", ("tokens", 4000))
        keep = summarization.get("keep", ("messages", 20))
        middleware.append(SummarizationMiddleware(
            model=summary_model,
            trigger=trigger,
            keep=keep,
        ))

    return middleware
