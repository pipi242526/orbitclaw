"""Chat POST action handlers for Web UI."""

from __future__ import annotations

import asyncio
import json
import queue
import re
import threading
from collections.abc import Awaitable, Callable
from typing import Any

from lunaeclaw.app.cli.runtime_wiring import build_agent_loop, make_provider
from lunaeclaw.core.bus.queue import MessageBus
from lunaeclaw.services.session.manager import SessionManager

_WEB_CHAT_AGENT_LOCK = threading.Lock()
_WEB_CHAT_TURN_LOCK = threading.Lock()
_WEB_CHAT_AGENT: Any | None = None
_WEB_CHAT_AGENT_FINGERPRINT = ""


def _normalize_chat_session_id(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "-", (raw or "").strip())[:40].strip("-_")
    return cleaned or "default"


def _config_fingerprint(cfg: Any) -> str:
    try:
        raw = cfg.model_dump(by_alias=True)
    except Exception:
        return repr(cfg)
    try:
        return json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return repr(raw)


async def _get_or_create_web_chat_agent(handler: Any, cfg: Any) -> Any:
    global _WEB_CHAT_AGENT, _WEB_CHAT_AGENT_FINGERPRINT
    fingerprint = _config_fingerprint(cfg)
    stale_agent: Any | None = None

    with _WEB_CHAT_AGENT_LOCK:
        if _WEB_CHAT_AGENT is not None and _WEB_CHAT_AGENT_FINGERPRINT == fingerprint:
            return _WEB_CHAT_AGENT

        stale_agent = _WEB_CHAT_AGENT
        bus = MessageBus(
            inbound_maxsize=cfg.agents.defaults.inbound_queue_maxsize,
            outbound_maxsize=cfg.agents.defaults.outbound_queue_maxsize,
        )
        provider = make_provider(cfg)
        session_manager = SessionManager(
            cfg.workspace_path,
            max_cache_entries=max(1, int(cfg.agents.defaults.session_cache_max_entries)),
        )
        _WEB_CHAT_AGENT = build_agent_loop(
            config=cfg,
            bus=bus,
            provider=provider,
            session_manager=session_manager,
        )
        _WEB_CHAT_AGENT_FINGERPRINT = fingerprint
        current = _WEB_CHAT_AGENT

    if stale_agent is not None:
        try:
            await stale_agent.close_mcp()
        except Exception:
            pass
    return current


async def _run_web_chat_turn(
    handler: Any,
    *,
    prompt: str,
    session_id: str,
    on_progress: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    cfg = handler._load_config()
    agent = await _get_or_create_web_chat_agent(handler, cfg)
    return await agent.process_direct(
        prompt,
        session_key=f"webui:{session_id}",
        channel="webui",
        chat_id=session_id,
        on_progress=on_progress,
    )


def _run_web_chat_turn_sync(
    handler: Any,
    *,
    prompt: str,
    session_id: str,
    on_progress: Callable[[str], Awaitable[None]] | None = None,
) -> str:
    # AgentLoop is process-local mutable state; serialize turns in WebUI server threads.
    if on_progress is None:
        coro = _run_web_chat_turn(
            handler,
            prompt=prompt,
            session_id=session_id,
        )
    else:
        coro = _run_web_chat_turn(
            handler,
            prompt=prompt,
            session_id=session_id,
            on_progress=on_progress,
        )
    with _WEB_CHAT_TURN_LOCK:
        return asyncio.run(coro)


def _chunk_stream_text(text: str, *, chunk_size: int = 72) -> list[str]:
    src = str(text or "")
    if not src:
        return []
    chunks: list[str] = []
    i = 0
    n = len(src)
    hard_min = max(16, chunk_size // 4)
    split_chars = "\n。！？.!?,，；;、 "
    while i < n:
        end = min(n, i + chunk_size)
        if end < n:
            pos = -1
            for c in split_chars:
                p = src.rfind(c, i, end)
                if p > pos:
                    pos = p
            if pos >= i + hard_min:
                end = pos + 1
        chunks.append(src[i:end])
        i = end
    return chunks


def _stream_chat_turn_sse(handler: Any, *, prompt: str, session_id: str) -> None:
    events: queue.Queue[tuple[str, str]] = queue.Queue()
    state: dict[str, str] = {"last_progress": ""}

    def _worker() -> None:
        async def _on_progress(content: str) -> None:
            text = str(content or "").strip()
            if not text:
                return
            if text == state["last_progress"]:
                return
            state["last_progress"] = text
            events.put(("progress", text))

        try:
            reply = _run_web_chat_turn_sync(
                handler,
                prompt=prompt,
                session_id=session_id,
                on_progress=_on_progress,
            )
            events.put(("final", str(reply or "")))
        except Exception as e:
            events.put(("error", str(e)))
        finally:
            events.put(("done", ""))

    thread = threading.Thread(target=_worker, name="webui-chat-stream", daemon=True)
    thread.start()

    try:
        handler._send_sse_headers(200)
        handler._send_sse_event("started", {"session_id": session_id})
        while True:
            try:
                kind, payload = events.get(timeout=0.8)
            except queue.Empty:
                handler._send_sse_comment("ping")
                continue
            if kind == "progress":
                handler._send_sse_event("progress", {"text": payload})
                continue
            if kind == "final":
                text = str(payload or "")
                for part in _chunk_stream_text(text):
                    handler._send_sse_event("delta", {"text": part})
                handler._send_sse_event("complete", {"text": text})
                continue
            if kind == "error":
                handler._send_sse_event("error", {"error": str(payload or "unknown error")})
                continue
            if kind == "done":
                handler._send_sse_event("done", {"ok": True})
                break
    except (BrokenPipeError, ConnectionResetError):
        return
    finally:
        thread.join(timeout=0.2)


def handle_post_chat(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /chat POST actions."""
    action = handler._form_str(form, "action").strip()
    session_id = _normalize_chat_session_id(handler._form_str(form, "session_id", "default"))
    zh = handler._ui_lang == "zh-CN"
    is_xhr = str(getattr(handler, "headers", {}).get("X-Requested-With", "")).lower() == "xmlhttprequest"

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
        if is_xhr:
            try:
                reply = _run_web_chat_turn_sync(handler, prompt=prompt, session_id=session_id)
            except Exception as e:
                handler._send_text(
                    500,
                    json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False),
                    content_type="application/json; charset=utf-8",
                )
                return
            handler._send_text(
                200,
                json.dumps(
                    {
                        "ok": True,
                        "session_id": session_id,
                        "reply": str(reply or ""),
                    },
                    ensure_ascii=False,
                ),
                content_type="application/json; charset=utf-8",
            )
            return
        _run_web_chat_turn_sync(handler, prompt=prompt, session_id=session_id)
        msg = "已收到，回复已更新。" if zh else "Turn completed."
        handler._redirect(f"/chat?session={session_id}", msg=msg)
        return

    if action == "chat_stream":
        prompt = handler._form_str(form, "message").strip()
        if not prompt:
            if is_xhr:
                handler._send_text(
                    400,
                    json.dumps({"ok": False, "error": "请输入消息内容。" if zh else "Message cannot be empty."}, ensure_ascii=False),
                    content_type="application/json; charset=utf-8",
                )
                return
            raise ValueError("请输入消息内容。" if zh else "Message cannot be empty.")
        _stream_chat_turn_sse(handler, prompt=prompt, session_id=session_id)
        return

    raise ValueError("不支持的聊天操作" if zh else "Unsupported chat action")
