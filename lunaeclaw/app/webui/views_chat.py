"""Chat page renderer for Web UI."""

from __future__ import annotations

import re
from html import escape
from typing import Any

from lunaeclaw.app.webui.icons import icon_svg
from lunaeclaw.services.session.manager import SessionManager


def _normalize_session_id(raw: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "-", (raw or "").strip())[:40].strip("-_")
    return cleaned or "default"


def render_chat(handler: Any, *, msg: str = "", err: str = "", session_id: str = "default") -> None:
    """Render chat page backed by local direct AgentLoop turns."""
    cfg = handler._load_config()
    zh = handler._ui_lang == "zh-CN"
    sid = _normalize_session_id(session_id)
    session_key = f"webui:{sid}"

    sessions = SessionManager(
        cfg.workspace_path,
        max_cache_entries=max(1, int(cfg.agents.defaults.session_cache_max_entries)),
    )
    current = sessions.get_or_create(session_key)
    history = [m for m in current.messages if m.get("role") in {"user", "assistant"}][-80:]

    known_ids = []
    for row in sessions.list_sessions():
        key = str(row.get("key") or "")
        if key.startswith("webui:"):
            known_ids.append(key.split(":", 1)[1])
    if sid not in known_ids:
        known_ids.insert(0, sid)
    known_ids = sorted({x for x in known_ids if x}, key=lambda x: (x != sid, x))
    options = "".join(
        f"<option value='{escape(name)}' {'selected' if name == sid else ''}>{escape(name)}</option>"
        for name in known_ids
    )

    items = []
    for m in history:
        role = "你" if zh and m.get("role") == "user" else "助手" if zh else "You" if m.get("role") == "user" else "Assistant"
        cls = "user" if m.get("role") == "user" else "assistant"
        items.append(
            "<div class='chat-item {cls}'>"
            "<div class='chat-role'>{role}</div>"
            "<pre class='chat-content'>{content}</pre>"
            "</div>".format(
                cls=cls,
                role=escape(role),
                content=escape(str(m.get("content") or "")),
            )
        )

    title = "Web Chat" if not zh else "网页聊天"
    icon_clear = icon_svg("clear")
    icon_send = icon_svg("send")
    body = f"""
<style>
  .chat-wrap {{ display:grid; gap:14px; }}
  .chat-board {{
    min-height: 360px;
    max-height: 62vh;
    overflow: auto;
    padding: 12px;
    border:1px solid var(--line);
    border-radius: 14px;
    background: linear-gradient(180deg, color-mix(in srgb, var(--card-strong) 92%, #fff 8%), color-mix(in srgb, var(--card) 88%, transparent));
    box-shadow: inset 0 1px 0 rgba(255,255,255,.35);
  }}
  .chat-item {{
    margin-bottom: 10px;
    border:1px solid var(--line);
    border-radius: 12px;
    padding: 10px;
    background: linear-gradient(180deg, color-mix(in srgb, var(--card-strong) 82%, #fff 18%), color-mix(in srgb, var(--card) 84%, transparent));
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 35%, transparent), 0 8px 18px color-mix(in srgb, var(--line) 34%, transparent);
  }}
  .chat-item.user {{
    border-color: color-mix(in srgb, var(--accent-2) 42%, var(--line));
    margin-left: 10%;
  }}
  .chat-item.assistant {{
    border-color: color-mix(in srgb, var(--accent) 34%, var(--line));
    margin-right: 10%;
  }}
  .chat-role {{ font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
  .chat-content {{
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.45;
    font-family: var(--sans);
  }}
  .chat-empty {{
    display:grid;
    place-items:center;
    color: var(--muted);
    min-height: 280px;
    border:1px dashed var(--line);
    border-radius: 12px;
  }}
  .chat-tools {{
    display:grid;
    gap:10px;
    grid-template-columns: minmax(260px, 420px);
    padding: 8px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: color-mix(in srgb, var(--subtle-bg) 82%, transparent);
  }}
  .chat-tools .field {{ margin-bottom:0; min-width: 220px; }}
  .chat-tools form {{
    margin: 0;
    padding: 0;
    background: transparent;
    border: none;
  }}
  .chat-session-form .field {{ margin-bottom: 0; }}
  .chat-clear-form {{ display:flex; justify-content:flex-start; }}
  .chat-input textarea {{ min-height: 140px; font-size: 14px; font-family: var(--sans); }}
  @media (max-width: 780px) {{
    .chat-item.user {{ margin-left: 0; }}
    .chat-item.assistant {{ margin-right: 0; }}
    .chat-tools {{ grid-template-columns: 1fr; }}
  }}
</style>
<section class="card chat-wrap">
  <div class="chat-tools">
    <form method="get" action="/chat" class="chat-session-form">
      <div class="field">
        <label>{"会话" if zh else "Session"}</label>
        <select name="session" onchange="this.form.submit()">{options}</select>
      </div>
    </form>
    <form method="post" class="chat-clear-form">
      <input type="hidden" name="action" value="chat_clear">
      <input type="hidden" name="session_id" value="{escape(sid)}">
      <button class="btn danger icon-btn" type="submit">{icon_clear}{"清空会话" if zh else "Clear Session"}</button>
    </form>
  </div>
  <div class="chat-board">
    {''.join(items) or f"<div class='chat-empty'>{'输入消息后开始对话。' if zh else 'Send your first message to start chatting.'}</div>"}
  </div>
  <form method="post" class="chat-input">
    <input type="hidden" name="action" value="chat_send">
    <input type="hidden" name="session_id" value="{escape(sid)}">
    <div class="field">
      <label>{"消息" if zh else "Message"}</label>
      <textarea name="message" placeholder="{'直接在这里和 LunaeClaw 对话。' if zh else 'Chat with LunaeClaw directly in this page.'}"></textarea>
    </div>
    <div class="row"><button class="btn primary icon-btn" type="submit">{icon_send}{"发送" if zh else "Send"}</button></div>
  </form>
</section>
"""
    handler._send_html(200, handler._page(title, body, tab="/chat", msg=msg, err=err))
