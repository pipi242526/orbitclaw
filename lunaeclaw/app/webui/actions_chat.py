"""Chat POST action handlers for Web UI."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from lunaeclaw.app.cli.runtime_wiring import build_agent_loop, make_provider
from lunaeclaw.core.bus.queue import MessageBus
from lunaeclaw.services.session.manager import SessionManager


def _normalize_chat_session_id(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "-", (raw or "").strip())[:40].strip("-_")
    return cleaned or "default"


async def _run_web_chat_turn(handler: Any, *, prompt: str, session_id: str) -> str:
    cfg = handler._load_config()
    bus = MessageBus(
        inbound_maxsize=cfg.agents.defaults.inbound_queue_maxsize,
        outbound_maxsize=cfg.agents.defaults.outbound_queue_maxsize,
    )
    provider = make_provider(cfg)
    session_manager = SessionManager(
        cfg.workspace_path,
        max_cache_entries=max(1, int(cfg.agents.defaults.session_cache_max_entries)),
    )
    agent = build_agent_loop(
        config=cfg,
        bus=bus,
        provider=provider,
        session_manager=session_manager,
    )
    try:
        return await agent.process_direct(
            prompt,
            session_key=f"webui:{session_id}",
            channel="webui",
            chat_id=session_id,
        )
    finally:
        await agent.close_mcp()


def handle_post_chat(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /chat POST actions."""
    action = handler._form_str(form, "action").strip()
    session_id = _normalize_chat_session_id(handler._form_str(form, "session_id", "default"))
    zh = handler._ui_lang == "zh-CN"

    if action == "chat_clear":
        cfg = handler._load_config()
        session_manager = SessionManager(
            cfg.workspace_path,
            max_cache_entries=max(1, int(cfg.agents.defaults.session_cache_max_entries)),
        )
        session = session_manager.get_or_create(f"webui:{session_id}")
        session.clear()
        session_manager.save(session)
        msg = "会话已清空。" if zh else "Session cleared."
        handler._redirect(f"/chat?session={session_id}", msg=msg)
        return

    if action == "chat_send":
        prompt = handler._form_str(form, "message").strip()
        if not prompt:
            raise ValueError("请输入消息内容。" if zh else "Message cannot be empty.")
        asyncio.run(_run_web_chat_turn(handler, prompt=prompt, session_id=session_id))
        msg = "已收到，回复已更新。" if zh else "Turn completed."
        handler._redirect(f"/chat?session={session_id}", msg=msg)
        return

    raise ValueError("不支持的聊天操作" if zh else "Unsupported chat action")
