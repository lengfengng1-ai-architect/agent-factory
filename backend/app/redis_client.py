import json
import redis
from datetime import datetime, timezone
from typing import List, Dict, Any

r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

MAX_HISTORY = 50


def get_chat_history(agent_id: int) -> List[Dict[str, Any]]:
    """Get chat history for an agent from Redis."""
    key = f"chat_history:{agent_id}"
    items = r.lrange(key, 0, -1)
    return [json.loads(item) for item in items]


def append_chat_message(agent_id: int, role: str, content: str):
    """Append a message to agent's chat history in Redis."""
    key = f"chat_history:{agent_id}"
    message = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    r.rpush(key, json.dumps(message, ensure_ascii=False))
    r.ltrim(key, -MAX_HISTORY, -1)


def clear_chat_history(agent_id: int):
    """Clear chat history for an agent."""
    key = f"chat_history:{agent_id}"
    r.delete(key)


def set_chat_partial(agent_id: int, content: str, ttl: int = 300):
    """Store partial generation content for an agent."""
    key = f"chat_partial:{agent_id}"
    r.set(key, content, ex=ttl)


def get_chat_partial(agent_id: int) -> str:
    """Get partial generation content for an agent."""
    key = f"chat_partial:{agent_id}"
    return r.get(key) or ""


def delete_chat_partial(agent_id: int):
    """Delete partial generation content for an agent."""
    key = f"chat_partial:{agent_id}"
    r.delete(key)


MAX_GROUP_HISTORY = 100


def get_group_chat_history(group_id: int) -> List[Dict[str, Any]]:
    """Get group chat history from Redis."""
    key = f"group_chat_history:{group_id}"
    items = r.lrange(key, 0, -1)
    return [json.loads(item) for item in items]


def append_group_chat_message(group_id: int, role: str, agent_id: int, agent_name: str, content: str):
    """Append a message to group chat history in Redis."""
    key = f"group_chat_history:{group_id}"
    message = {
        "role": role,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    r.rpush(key, json.dumps(message, ensure_ascii=False))
    r.ltrim(key, -MAX_GROUP_HISTORY, -1)
