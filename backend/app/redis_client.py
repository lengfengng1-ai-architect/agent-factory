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
