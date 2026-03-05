"""Chat page renderer for Web UI."""

from __future__ import annotations

import re
from typing import Any

from lunaeclaw.app.webui.html_utils import escape
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
    user_label = "你" if zh else "You"
    assistant_label = "助手" if zh else "Assistant"
    typing_label = "思考中…" if zh else "Thinking..."
    send_label = "发送" if zh else "Send"
    sending_label = "发送中…" if zh else "Sending..."
    send_error_label = "发送失败，请重试。" if zh else "Failed to send. Please retry."
    icon_clear = icon_svg("clear")
    icon_send = icon_svg("send")
    body = f"""
<style>
  .chat-wrap {{ display:grid; gap:14px; }}
  .chat-board {{
    display: flex;
    flex-direction: column;
    gap: 10px;
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
    margin-bottom: 0;
    width: fit-content;
    max-width: min(68%, 780px);
    border:1px solid var(--line);
    border-radius: 12px;
    padding: 10px;
    background: linear-gradient(180deg, color-mix(in srgb, var(--card-strong) 82%, #fff 18%), color-mix(in srgb, var(--card) 84%, transparent));
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 35%, transparent), 0 8px 18px color-mix(in srgb, var(--line) 34%, transparent);
  }}
  .chat-item.user {{
    align-self: flex-end;
    border-color: color-mix(in srgb, var(--accent-2) 42%, var(--line));
    border-bottom-right-radius: 6px;
  }}
  .chat-item.assistant {{
    align-self: flex-start;
    border-color: color-mix(in srgb, var(--accent) 34%, var(--line));
    border-bottom-left-radius: 6px;
  }}
  .chat-item.pending {{
    border-style: dashed;
    opacity: .9;
  }}
  .chat-role {{ font-size: 12px; color: var(--muted); margin-bottom: 6px; }}
  .chat-content {{
    margin: 0;
    white-space: pre-wrap;
    word-break: break-word;
    line-height: 1.45;
    font-family: var(--sans);
  }}
  .chat-content.typing::after {{
    content: " ···";
    letter-spacing: 2px;
    animation: chatPulse 1s infinite steps(3, end);
  }}
  @keyframes chatPulse {{
    0% {{ opacity: .35; }}
    50% {{ opacity: 1; }}
    100% {{ opacity: .35; }}
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
  .chat-input .btn[disabled] {{ opacity: .72; cursor: not-allowed; }}
  @media (max-width: 780px) {{
    .chat-item {{ max-width: 100%; }}
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
  <form method="post" class="chat-input" id="chat-input-form">
    <input type="hidden" name="action" value="chat_send">
    <input type="hidden" name="session_id" value="{escape(sid)}">
    <div class="field">
      <label>{"消息" if zh else "Message"}</label>
      <textarea name="message" placeholder="{'直接在这里和 LunaeClaw 对话。' if zh else 'Chat with LunaeClaw directly in this page.'}" id="chat-input-message"></textarea>
    </div>
    <div class="row"><button class="btn primary icon-btn" type="submit" id="chat-send-btn">{icon_send}{send_label}</button></div>
  </form>
</section>
<script>
  (function bindAsyncChatSend() {{
    const form = document.getElementById("chat-input-form");
    const board = document.querySelector(".chat-board");
    const input = document.getElementById("chat-input-message");
    const sendBtn = document.getElementById("chat-send-btn");
    if (!form || !board || !input || !sendBtn || !window.fetch) return;
    board.scrollTop = board.scrollHeight;

    function removeEmptyHint() {{
      const empty = board.querySelector(".chat-empty");
      if (empty) empty.remove();
    }}

    function appendMessage(roleClass, roleLabel, text, isTyping) {{
      const item = document.createElement("div");
      item.className = `chat-item ${{roleClass}}${{isTyping ? " pending" : ""}}`;
      const role = document.createElement("div");
      role.className = "chat-role";
      role.textContent = roleLabel;
      const content = document.createElement("pre");
      content.className = `chat-content${{isTyping ? " typing" : ""}}`;
      content.textContent = text;
      item.appendChild(role);
      item.appendChild(content);
      board.appendChild(item);
      board.scrollTop = board.scrollHeight;
      return item;
    }}

    function setPendingText(node, text, typing) {{
      if (!node) return;
      node.classList.remove("pending");
      const content = node.querySelector(".chat-content");
      if (!content) return;
      content.textContent = String(text || "");
      if (typing) {{
        content.classList.add("typing");
      }} else {{
        content.classList.remove("typing");
      }}
      board.scrollTop = board.scrollHeight;
    }}

    async function sendStream(payload, pending) {{
      payload.set("action", "chat_stream");
      const resp = await fetch(window.location.pathname + window.location.search, {{
        method: "POST",
        headers: {{
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          "X-Requested-With": "XMLHttpRequest",
          "Accept": "text/event-stream"
        }},
        body: payload.toString()
      }});
      if (!resp.ok || !resp.body) {{
        let err = `HTTP ${{resp.status}}`;
        try {{
          const data = await resp.json();
          if (data && data.error) err = String(data.error);
        }} catch (e) {{}}
        throw new Error(err);
      }}
      const ct = (resp.headers.get("content-type") || "").toLowerCase();
      if (!ct.includes("text/event-stream")) {{
        throw new Error("invalid stream response");
      }}

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let streamed = "";
      let gotAny = false;

      while (true) {{
        const next = await reader.read();
        if (next.done) break;
        buffer += decoder.decode(next.value, {{ stream: true }});
        buffer = buffer.replace(/\\r/g, "");
        let sep = buffer.indexOf("\\n\\n");
        while (sep >= 0) {{
          const block = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          sep = buffer.indexOf("\\n\\n");
          if (!block.trim() || block.startsWith(":")) continue;

          let eventName = "message";
          const dataLines = [];
          for (const line of block.split("\\n")) {{
            if (line.startsWith("event:")) {{
              eventName = line.slice(6).trim();
            }} else if (line.startsWith("data:")) {{
              dataLines.push(line.slice(5).trimStart());
            }}
          }}

          const raw = dataLines.join("\\n");
          let data = {{}};
          if (raw) {{
            try {{
              data = JSON.parse(raw);
            }} catch (e) {{
              data = {{ text: raw }};
            }}
          }}

          if (eventName === "progress") {{
            if (!streamed) {{
              setPendingText(pending, data.text || "{escape(typing_label)}", true);
              gotAny = true;
            }}
          }} else if (eventName === "delta") {{
            streamed += String(data.text || "");
            setPendingText(pending, streamed, false);
            gotAny = true;
          }} else if (eventName === "complete") {{
            streamed = String(data.text || streamed || "");
            setPendingText(pending, streamed, false);
            gotAny = true;
          }} else if (eventName === "error") {{
            throw new Error(String(data.error || "stream failed"));
          }}
        }}
      }}

      if (!gotAny) {{
        setPendingText(pending, "{escape(send_error_label)}", false);
      }}
    }}

    let isComposing = false;
    input.addEventListener("compositionstart", () => {{
      isComposing = true;
    }});
    input.addEventListener("compositionend", () => {{
      isComposing = false;
    }});
    input.addEventListener("keydown", (event) => {{
      if (event.key !== "Enter") return;
      if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return;
      if (isComposing || event.isComposing) return;
      event.preventDefault();
      if (sendBtn.disabled) return;
      if (typeof form.requestSubmit === "function") {{
        form.requestSubmit();
      }} else {{
        form.dispatchEvent(new Event("submit", {{ cancelable: true, bubbles: true }}));
      }}
    }});

    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      const message = (input.value || "").trim();
      if (!message) return;

      removeEmptyHint();
      appendMessage("user", "{escape(user_label)}", message, false);
      const pending = appendMessage("assistant", "{escape(assistant_label)}", "{escape(typing_label)}", true);

      const formData = new FormData(form);
      const payload = new URLSearchParams();
      for (const [k, v] of formData.entries()) {{
        payload.append(k, String(v));
      }}

      sendBtn.disabled = true;
      const sendText = sendBtn.lastChild;
      if (sendText && sendText.nodeType === Node.TEXT_NODE) {{
        sendText.textContent = "{escape(sending_label)}";
      }}
      input.value = "";

      try {{
        await sendStream(payload, pending);
      }} catch (e) {{
        setPendingText(pending, "{escape(send_error_label)}", false);
      }} finally {{
        sendBtn.disabled = false;
        const sendTextRestore = sendBtn.lastChild;
        if (sendTextRestore && sendTextRestore.nodeType === Node.TEXT_NODE) {{
          sendTextRestore.textContent = "{escape(send_label)}";
        }}
        input.focus();
      }}
    }});
  }})();
</script>
"""
    handler._send_html(200, handler._page(title, body, tab="/chat", msg=msg, err=err))
