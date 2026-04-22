"""Feishu (Lark) OpenAPI client for sending messages and managing tokens."""

import json
import time
import requests

_token_cache: dict[str, tuple[str, float]] = {}


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    """Get tenant_access_token from Feishu OpenAPI. Cached until expiry."""
    cached = _token_cache.get(app_id)
    if cached and cached[1] > time.time():
        return cached[0]
    
    resp = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=10,
    )
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu auth error: {data}")
    
    token = data["tenant_access_token"]
    expire = time.time() + data.get("expire", 7200) - 300
    _token_cache[app_id] = (token, expire)
    return token


def send_text_message(app_id: str, app_secret: str, receive_id: str, text: str) -> dict:
    """Send a text message to a Feishu user or group chat."""
    token = get_tenant_access_token(app_id, app_secret)
    resp = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        params={"receive_id_type": "open_id"},
        json={
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}),
        },
        timeout=30,
    )
    return resp.json()
