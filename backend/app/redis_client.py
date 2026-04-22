import json
import os
import redis
from datetime import datetime, timezone
from typing import List, Dict, Any


def _create_redis_client() -> redis.Redis:
    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        return redis.from_url(redis_url, decode_responses=True)

    host = os.environ.get("REDIS_HOST", "localhost")
    port = int(os.environ.get("REDIS_PORT", "6379"))
    db = int(os.environ.get("REDIS_DB", "0"))
    return redis.Redis(host=host, port=port, db=db, decode_responses=True)


r = _create_redis_client()

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


# ── Feishu chat history (isolated from web chat) ──

def get_feishu_chat_history(agent_id: int) -> List[Dict[str, Any]]:
    """Get Feishu chat history for an agent from Redis."""
    key = f"feishu_chat_history:{agent_id}"
    items = r.lrange(key, 0, -1)
    return [json.loads(item) for item in items]


def append_feishu_chat_message(agent_id: int, role: str, content: str):
    """Append a message to agent's Feishu chat history in Redis."""
    key = f"feishu_chat_history:{agent_id}"
    message = {
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    r.rpush(key, json.dumps(message, ensure_ascii=False))
    r.ltrim(key, -MAX_HISTORY, -1)


def clear_feishu_chat_history(agent_id: int):
    """Clear Feishu chat history for an agent."""
    key = f"feishu_chat_history:{agent_id}"
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


# ── Chat file metadata storage ──

def get_chat_files(agent_id: int) -> List[Dict[str, Any]]:
    """Get uploaded file metadata for an agent."""
    key = f"chat_files:{agent_id}"
    items = r.lrange(key, 0, -1)
    return [json.loads(item) for item in items]


def add_chat_file(agent_id: int, file_meta: Dict[str, Any]):
    """Add a file metadata entry for an agent."""
    key = f"chat_files:{agent_id}"
    r.rpush(key, json.dumps(file_meta, ensure_ascii=False))


def remove_chat_file(agent_id: int, file_id: str):
    """Remove a file metadata entry by file_id."""
    key = f"chat_files:{agent_id}"
    items = r.lrange(key, 0, -1)
    for item in items:
        data = json.loads(item)
        if data.get("id") == file_id:
            r.lrem(key, 0, item)
            break


def clear_chat_files(agent_id: int):
    """Clear all file metadata for an agent."""
    r.delete(f"chat_files:{agent_id}")


# ── Group chat file metadata storage ──

def get_group_chat_files(group_id: int) -> List[Dict[str, Any]]:
    """Get uploaded file metadata for a group."""
    key = f"group_chat_files:{group_id}"
    items = r.lrange(key, 0, -1)
    return [json.loads(item) for item in items]


def add_group_chat_file(group_id: int, file_meta: Dict[str, Any]):
    """Add a file metadata entry for a group."""
    key = f"group_chat_files:{group_id}"
    r.rpush(key, json.dumps(file_meta, ensure_ascii=False))


def remove_group_chat_file(group_id: int, file_id: str):
    """Remove a file metadata entry by file_id."""
    key = f"group_chat_files:{group_id}"
    items = r.lrange(key, 0, -1)
    for item in items:
        data = json.loads(item)
        if data.get("id") == file_id:
            r.lrem(key, 0, item)
            break


def clear_group_chat_files(group_id: int):
    """Clear all file metadata for a group."""
    r.delete(f"group_chat_files:{group_id}")
