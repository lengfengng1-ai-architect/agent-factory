"""Feishu WebSocket long-connection client manager."""

import threading
from typing import Optional

import lark_oapi as lark
from lark_oapi import JSON
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1

from app import models
from app.database import SessionLocal
from app.feishu_client import send_text_message
from app.redis_client import append_feishu_chat_message, get_feishu_chat_history
from app.llm_factory import create_llm
from langchain.messages import HumanMessage, SystemMessage, AIMessage

# Map: agent_id -> ws_client thread
_ws_threads: dict[int, threading.Thread] = {}


async def _reply_to_feishu(agent_id: int, receive_id: str, text: str):
    """Generate reply via Agent LLM and send back to Feishu."""
    db = SessionLocal()
    try:
        agent = db.query(models.Agent).filter(models.Agent.id == agent_id).first()
        if not agent:
            return

        provider = db.query(models.Provider).filter(
            models.Provider.key == (agent.provider or "kimi").lower()
        ).first()
        if not provider or not provider.is_enabled:
            return

        llm = create_llm(agent, provider, streaming=False, max_tokens=2000)

        # Save user message to Redis (isolated feishu history)
        append_feishu_chat_message(agent_id, "user", text)

        # Load Feishu chat history for context
        history = get_feishu_chat_history(agent_id)

        messages = [SystemMessage(content=agent.system_prompt or "You are a helpful assistant.")]
        for msg in history[:-1]:  # Exclude the last user message we just added
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))
        messages.append(HumanMessage(content=f"【飞书消息】{text}"))

        response = await llm.ainvoke(messages)
        reply = response.content.strip()

        # Save assistant reply to Redis (isolated feishu history)
        append_feishu_chat_message(agent_id, "assistant", reply)

        feishu_cfg = (agent.config or {}).get("feishu", {})
        app_id = feishu_cfg.get("app_id", "")
        app_secret = feishu_cfg.get("app_secret", "")
        if app_id and app_secret:
            send_text_message(app_id, app_secret, receive_id, reply)
    finally:
        db.close()


def _create_event_handler(agent_id: int):
    """Create an event handler bound to a specific agent."""
    def handle_p2_im_message(data: P2ImMessageReceiveV1) -> None:
        import json
        import asyncio

        data_dict = json.loads(JSON.marshal(data))
        msg = data_dict.get("event", {}).get("message", {})
        msg_type = msg.get("message_type", "")

        if msg_type != "text":
            return

        content = json.loads(msg.get("content", "{}"))
        text = content.get("text", "").strip()
        if not text:
            return

        sender_id = data_dict.get("event", {}).get("sender", {}).get("sender_id", {}).get("open_id", "")
        if not sender_id:
            return

        # Run async reply in a new event loop (since this is a sync callback from SDK)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_reply_to_feishu(agent_id, sender_id, text))
            else:
                loop.run_until_complete(_reply_to_feishu(agent_id, sender_id, text))
        except RuntimeError:
            # No event loop in this thread
            asyncio.run(_reply_to_feishu(agent_id, sender_id, text))

    return handle_p2_im_message


def start_feishu_ws(agent: models.Agent) -> bool:
    """Start a WebSocket client for an agent's Feishu bot in a background thread."""
    feishu_cfg = (agent.config or {}).get("feishu", {})
    if not feishu_cfg.get("enabled"):
        return False

    app_id = feishu_cfg.get("app_id", "")
    app_secret = feishu_cfg.get("app_secret", "")
    if not app_id or not app_secret:
        return False

    if agent.id in _ws_threads and _ws_threads[agent.id].is_alive():
        return True  # already running

    try:
        event_handler = lark.EventDispatcherHandler.builder("", "") \
            .register_p2_im_message_receive_v1(_create_event_handler(agent.id)) \
            .build()

        cli = lark.ws.Client(
            app_id,
            app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        def _run():
            try:
                # lark-oapi 在模块导入时缓存了主线程的 event loop，
                # daemon 线程中需要创建自己的 loop 并替换模块全局变量
                import asyncio
                import lark_oapi.ws.client as _ws_mod
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                _ws_mod.loop = new_loop
                cli.start()
            except Exception as e:
                print(f"Feishu WS for agent {agent.id} error: {e}")

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        _ws_threads[agent.id] = t
        return True
    except Exception as e:
        print(f"Failed to start Feishu WS for agent {agent.id}: {e}")
        return False


def stop_feishu_ws(agent_id: int):
    """Stop a WebSocket client thread."""
    # Note: lark-oapi ws.Client does not expose a clean stop() method.
    # We mark the thread reference but cannot cleanly interrupt it.
    # The daemon thread will die when the main process exits.
    _ws_threads.pop(agent_id, None)


def stop_all_feishu_ws():
    """Stop all WebSocket clients."""
    for agent_id in list(_ws_threads.keys()):
        stop_feishu_ws(agent_id)


def get_ws_status(agent_id: int) -> dict:
    """Get connection status for an agent's Feishu bot."""
    t = _ws_threads.get(agent_id)
    return {
        "connected": t is not None and t.is_alive(),
        "agent_id": agent_id,
    }
