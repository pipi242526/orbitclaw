"""Minimal local web UI for managing nanobot config."""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import webbrowser
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from nanobot.config.loader import get_config_path, load_config, save_config
from nanobot.config.schema import (
    ChannelsConfig,
    Config,
    EndpointProviderConfig,
    MCPServerConfig,
    SkillsConfig,
    ToolsConfig,
)
from nanobot.utils.helpers import get_env_dir, get_env_file, get_global_skills_path, get_media_dir


_ENDPOINT_TYPES = [
    "openai_compatible",
    "anthropic",
    "openai",
    "openrouter",
    "deepseek",
    "groq",
    "gemini",
    "zhipu",
    "dashscope",
    "moonshot",
    "minimax",
    "vllm",
    "aihubmix",
    "siliconflow",
    "volcengine",
]


def _merge_unique(items: list[str], additions: list[str]) -> list[str]:
    out: list[str] = []
    for value in [*(items or []), *(additions or [])]:
        v = str(value).strip()
        if v and v not in out:
            out.append(v)
    return out


def _apply_recommended_tool_defaults(config: Config) -> None:
    """Mirror CLI onboarding lightweight defaults for UI users."""
    tools = config.tools
    if not tools.web.search.provider or tools.web.search.provider not in {"exa_mcp", "disabled"}:
        tools.web.search.provider = "exa_mcp"
    if "exa" not in tools.mcp_servers:
        tools.mcp_servers["exa"] = MCPServerConfig(
            url="https://mcp.exa.ai/mcp?tools=web_search_exa,get_code_context_exa"
        )
    if "docloader" not in tools.mcp_servers:
        tools.mcp_servers["docloader"] = MCPServerConfig(
            command="uvx",
            args=["awslabs.document-loader-mcp-server@latest"],
            env={"FASTMCP_LOG_LEVEL": "ERROR"},
        )
    tools.mcp_enabled_servers = _merge_unique(tools.mcp_enabled_servers, ["exa", "docloader"])
    tools.mcp_enabled_tools = _merge_unique(
        tools.mcp_enabled_tools,
        ["web_search_exa", "get_code_context_exa", "read_document", "read_image"],
    )
    tools.aliases.setdefault("code_search", "mcp_exa_get_code_context_exa")
    tools.aliases.setdefault("doc_read", "mcp_docloader_read_document")
    tools.aliases.setdefault("image_read", "mcp_docloader_read_image")


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in (value or "").replace("\n", ",").split(",") if item.strip()]


def _pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _mask_secret(value: str | None) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return f"{s[:4]}...{s[-4:]}"


def _safe_json_object(raw: str, field_name: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as e:
        raise ValueError(f"{field_name} JSON parse error: {e}") from e
    if not isinstance(data, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    return data


def _collect_skill_rows(config: Config) -> list[dict[str, Any]]:
    try:
        from nanobot.agent.skills import SkillsLoader
    except Exception as e:
        return [
            {
                "name": "_skills_loader_unavailable",
                "source": "system",
                "path": "",
                "available": False,
                "requires": f"Import error: {e}",
                "disabled": False,
            }
        ]
    loader = SkillsLoader(config.workspace_path, disabled_skills=set(config.skills.disabled or []))
    availability = {row["name"]: row for row in loader.build_availability_report()}
    rows: list[dict[str, Any]] = []
    for item in loader.list_skills(filter_unavailable=False):
        name = item["name"]
        diag = availability.get(name, {})
        rows.append(
            {
                "name": name,
                "source": item.get("source") or "",
                "path": item.get("path") or "",
                "available": bool(diag.get("available", True)),
                "requires": str(diag.get("requires") or ""),
                "disabled": name in (config.skills.disabled or []),
            }
        )
    rows.sort(key=lambda r: (r["disabled"], r["source"], r["name"]))
    return rows


def _media_display_name(name: str) -> str:
    if "_" in name:
        prefix, rest = name.split("_", 1)
        if prefix and len(prefix) >= 8 and rest:
            return rest
    return name


def _list_media_rows() -> list[dict[str, Any]]:
    media_dir = get_media_dir()
    rows: list[dict[str, Any]] = []
    if not media_dir.exists():
        return rows
    for p in sorted(media_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file():
            continue
        st = p.stat()
        rows.append(
            {
                "name": p.name,
                "display_name": _media_display_name(p.name),
                "size": st.st_size,
                "mtime": st.st_mtime,
                "path": str(p),
            }
        )
    return rows


def run_webui(
    host: str = "127.0.0.1",
    port: int = 18791,
    *,
    config_path: Path | None = None,
    open_browser: bool = False,
    path_token: str | None = None,
) -> None:
    """Start the local nanobot web UI."""
    cfg_path = (config_path or get_config_path()).expanduser()
    path_token = (path_token or "").strip()
    token_path = cfg_path.parent / "webui.path-token"

    def _normalize_path_token(raw: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_-]", "", (raw or "").strip().strip("/"))
        if len(cleaned) < 12:
            raise ValueError("Web UI path token must be at least 12 URL-safe chars")
        return cleaned

    def _resolve_path_token() -> str:
        nonlocal path_token
        if path_token:
            path_token = _normalize_path_token(path_token)
            return path_token
        if token_path.exists():
            try:
                path_token = _normalize_path_token(token_path.read_text(encoding="utf-8").strip())
            except Exception:
                path_token = ""
            if path_token:
                print(f"🔐 Web UI path token loaded from {token_path}", flush=True)
                return path_token
        path_token = secrets.token_urlsafe(15)  # ~20 chars, URL-safe
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(path_token + "\n", encoding="utf-8")
        try:
            os.chmod(token_path, 0o600)
        except Exception:
            pass
        print(f"🔐 Web UI path token generated (first start): {path_token}", flush=True)
        print(f"🔐 Saved token to: {token_path}", flush=True)
        return path_token

    path_token = _resolve_path_token()
    path_prefix = f"/{path_token}"

    class Handler(BaseHTTPRequestHandler):
        server_version = "nanobot-webui/0.1"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return  # keep CLI clean

        def do_HEAD(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path or "/"
            if path in {"/healthz", f"{path_prefix}/healthz"}:
                self._send_text(200, "ok", head_only=True)
                return
            route_path = self._route_path(path)
            if route_path is None:
                self._send_text(404, "Not Found", head_only=True)
                return
            if route_path in {"/", "/endpoints", "/channels", "/extensions", "/media"}:
                self._send_text(200, "", head_only=True)
                return
            self._send_text(404, "Not Found", head_only=True)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path or "/"
            if path in {"/healthz", f"{path_prefix}/healthz"}:
                self._send_text(200, "ok")
                return
            route_path = self._route_path(path)
            if route_path is None:
                self._send_text(404, "Not Found")
                return
            params = parse_qs(parsed.query)
            msg = (params.get("msg") or [""])[0]
            err = (params.get("err") or [""])[0]
            try:
                if route_path == "/":
                    self._render_dashboard(msg=msg, err=err)
                elif route_path == "/endpoints":
                    self._render_endpoints(msg=msg, err=err)
                elif route_path == "/channels":
                    self._render_channels(msg=msg, err=err)
                elif route_path == "/extensions":
                    self._render_extensions(msg=msg, err=err)
                elif route_path == "/media":
                    self._render_media(msg=msg, err=err)
                else:
                    self._send_html(404, self._page("Not Found", "<p>Not Found</p>", tab=""))
            except Exception as e:  # keep UI resilient
                self._send_html(500, self._page("Error", f"<pre>{escape(str(e))}</pre>", tab=""))

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            route_path = self._route_path(parsed.path or "/")
            if route_path is None:
                self._send_text(404, "Not Found")
                return
            form = self._read_form()
            try:
                if route_path == "/endpoints":
                    self._handle_post_endpoints(form)
                    return
                if route_path == "/channels":
                    self._handle_post_channels(form)
                    return
                if route_path == "/extensions":
                    self._handle_post_extensions(form)
                    return
                if route_path == "/media":
                    self._handle_post_media(form)
                    return
                self._redirect("/", err="Unsupported action")
            except Exception as e:
                target = route_path if route_path in {"/endpoints", "/channels", "/extensions", "/media"} else "/"
                self._redirect(target, err=str(e))

        def _load_config(self) -> Config:
            return load_config(cfg_path, apply_profiles=False, resolve_env=False)

        def _save_config(self, config: Config) -> None:
            save_config(config, cfg_path)

        def _read_form(self) -> dict[str, list[str]]:
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            return parse_qs(raw, keep_blank_values=True)

        def _form_str(self, form: dict[str, list[str]], key: str, default: str = "") -> str:
            return (form.get(key) or [default])[0]

        def _form_bool(self, form: dict[str, list[str]], key: str) -> bool:
            return key in form and (self._form_str(form, key).lower() not in {"0", "false", "off"})

        def _send_html(self, status: int, html: str) -> None:
            html = self._rewrite_prefixed_paths(html)
            data = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_text(
            self,
            status: int,
            text: str,
            *,
            head_only: bool = False,
            content_type: str = "text/plain; charset=utf-8",
        ) -> None:
            data = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if not head_only:
                self.wfile.write(data)

        def _route_path(self, raw_path: str) -> str | None:
            if not path_prefix:
                return raw_path or "/"
            if raw_path == path_prefix:
                return "/"
            if raw_path.startswith(path_prefix + "/"):
                suffix = raw_path[len(path_prefix):]
                return suffix or "/"
            return None

        def _rewrite_prefixed_paths(self, html_doc: str) -> str:
            if not path_prefix:
                return html_doc
            return re.sub(
                r'(?P<attr>href|action|formaction)="/(?P<path>(?!/)[^"]*)"',
                lambda m: f'{m.group("attr")}="{path_prefix}/{m.group("path")}"',
                html_doc,
            )

        def _redirect(self, path: str, *, msg: str = "", err: str = "") -> None:
            params: dict[str, str] = {}
            if msg:
                params["msg"] = msg
            if err:
                params["err"] = err
            url = f"{path_prefix}{path}" if path_prefix and path.startswith("/") else path
            if params:
                url = f"{url}?{urlencode(params)}"
            self.send_response(303)
            self.send_header("Location", url)
            self.end_headers()

        def _nav(self, tab: str) -> str:
            items = [
                ("/", "Dashboard"),
                ("/endpoints", "Models & APIs"),
                ("/channels", "Channels"),
                ("/extensions", "MCP & Skills"),
                ("/media", "Media"),
            ]
            links = []
            for href, label in items:
                active = "active" if tab == href else ""
                links.append(f'<a class="nav-item {active}" href="{href}">{escape(label)}</a>')
            return "".join(links)

        def _page(self, title: str, body: str, *, tab: str, msg: str = "", err: str = "") -> str:
            flash = ""
            if msg:
                flash += f'<div class="flash ok">{escape(msg)}</div>'
            if err:
                flash += f'<div class="flash err">{escape(err)}</div>'
            external_host = "127.0.0.1" if host == "0.0.0.0" else host
            full_access_url = f"http://{external_host}:{port}{path_prefix}/"
            return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - nanobot Web UI</title>
  <style>
    :root {{
      --bg: #f2efe8;
      --card: #fffdf8;
      --ink: #1f2328;
      --muted: #5b6470;
      --line: #d7d0c2;
      --accent: #0f6c5c;
      --accent-2: #d96f2b;
      --err: #b42318;
      --ok: #067647;
      --shadow: 0 8px 28px rgba(31,35,40,.08);
      --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      --sans: "Avenir Next", "PingFang SC", "Noto Sans SC", "Helvetica Neue", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 0; font-family: var(--sans); color: var(--ink);
      background:
        radial-gradient(circle at 10% 10%, rgba(217,111,43,.10), transparent 40%),
        radial-gradient(circle at 90% 0%, rgba(15,108,92,.10), transparent 35%),
        var(--bg);
    }}
    .layout {{ max-width: 1200px; margin: 0 auto; padding: 18px; }}
    .top {{
      display:flex; align-items:flex-start; justify-content:space-between; gap:16px; margin-bottom:16px;
      background: linear-gradient(180deg, rgba(255,255,255,.7), rgba(255,255,255,.35));
      border:1px solid rgba(255,255,255,.9); box-shadow: var(--shadow); border-radius: 16px; padding: 14px;
      backdrop-filter: blur(6px);
    }}
    .brand h1 {{ margin:0; font-size: 22px; letter-spacing:.2px; }}
    .brand p {{ margin:6px 0 0; color: var(--muted); font-size: 13px; }}
    .access-chip {{
      margin-top: 10px; display:inline-flex; align-items:center; gap:8px; border:1px dashed #cdbfa8;
      background: rgba(255,255,255,.65); color: #523e1a; border-radius: 999px; padding: 6px 10px;
      font-size: 12px; font-family: var(--mono);
    }}
    .nav {{ display:flex; gap:8px; flex-wrap:wrap; }}
    .nav-item {{
      text-decoration:none; color: var(--ink); border:1px solid var(--line);
      background: rgba(255,255,255,.55); padding:8px 12px; border-radius: 999px; font-size: 13px;
      transition: transform .12s ease, box-shadow .12s ease, background .12s ease;
    }}
    .nav-item:hover {{ transform: translateY(-1px); box-shadow: 0 4px 14px rgba(31,35,40,.08); }}
    .nav-item.active {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    .flash {{ border-radius: 10px; padding: 10px 12px; margin-bottom: 12px; font-size: 13px; }}
    .flash.ok {{ background: #ecfdf3; color: var(--ok); border:1px solid #abefc6; }}
    .flash.err {{ background: #fef3f2; color: var(--err); border:1px solid #fecdca; }}
    .grid {{ display:grid; gap: 14px; }}
    .grid.cols-2 {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .grid.cols-3 {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    .card {{
      background: var(--card); border:1px solid var(--line); border-radius: 14px; box-shadow: var(--shadow);
      padding: 14px;
    }}
    .card h2 {{ margin:0 0 10px; font-size: 16px; }}
    .card h3 {{ margin:0 0 8px; font-size: 14px; }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .kpi {{ font-size: 28px; font-weight: 700; }}
    .row {{ display:flex; gap:10px; align-items:center; flex-wrap:wrap; }}
    .field {{ display:grid; gap:6px; margin-bottom:10px; }}
    .field label {{ font-size: 12px; color: var(--muted); }}
    input[type=text], input[type=number], textarea, select {{
      width:100%; border:1px solid var(--line); border-radius:10px; background:#fff; color:var(--ink);
      padding:10px 12px; font: inherit;
    }}
    textarea {{ min-height: 120px; font-family: var(--mono); font-size: 12px; line-height: 1.35; }}
    .mono {{ font-family: var(--mono); font-size: 12px; }}
    .btn {{
      border:1px solid var(--line); background:#fff; color: var(--ink); border-radius: 10px;
      padding:8px 12px; cursor:pointer; font-weight:600;
    }}
    .btn.primary {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    .btn.warn {{ background: var(--accent-2); color: #fff; border-color: var(--accent-2); }}
    .btn.subtle {{ background: rgba(255,255,255,.55); }}
    table {{ width:100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom:1px solid #ece7dc; text-align:left; vertical-align: top; padding:8px 6px; }}
    th {{ color: var(--muted); font-weight:600; }}
    tbody tr:hover td {{ background: rgba(15,108,92,.03); }}
    code {{ font-family: var(--mono); background:#f4f1ea; padding:2px 4px; border-radius:4px; }}
    .pill {{ display:inline-block; border-radius:999px; padding:2px 8px; font-size:11px; border:1px solid var(--line); }}
    .pill.ok {{ border-color:#abefc6; color: var(--ok); background:#f0fdf4; }}
    .pill.off {{ border-color:#fecdca; color: var(--err); background:#fef2f2; }}
    .split {{ display:grid; grid-template-columns: 1.15fr .85fr; gap: 14px; }}
    .small {{ font-size: 12px; }}
    .list {{ margin:0; padding-left: 18px; }}
    .list li {{ margin: 4px 0; }}
    .endpoint-card {{ border:1px solid #ece7dc; border-radius: 12px; padding: 12px; margin-bottom:10px; background:#fff; }}
    .endpoint-head {{ display:flex; justify-content:space-between; gap:8px; align-items:center; }}
    .endpoint-fields {{ display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:10px; margin-top:10px; }}
    .endpoint-fields .field.full {{ grid-column: 1 / -1; }}
    .toast {{
      position: fixed; right: 16px; bottom: 16px; background: #122b24; color: #fff; border-radius: 10px;
      padding: 10px 12px; font-size: 12px; opacity: 0; transform: translateY(8px); pointer-events:none;
      transition: all .18s ease;
    }}
    .toast.show {{ opacity: .96; transform: translateY(0); }}
    @media (max-width: 900px) {{
      .grid.cols-2, .grid.cols-3, .split, .endpoint-fields {{ grid-template-columns: 1fr; }}
      .top {{ flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <div class="layout">
    <div class="top">
      <div class="brand">
        <h1>nanobot Web UI</h1>
        <p>轻量配置管理台（Host: {escape(host)}:{port}） · 使用路径密钥访问（无账号密码弹窗）</p>
        <div class="access-chip">
          <span>路径密钥已启用（页面不展示密钥）</span>
          <button type="button" class="btn" data-copy="{escape(full_access_url)}" onclick="nbCopy(this.dataset.copy)">复制入口地址</button>
          <button type="button" class="btn subtle" onclick="nbCopy(window.location.href)">复制当前页面地址</button>
        </div>
      </div>
      <nav class="nav">{self._nav(tab)}</nav>
    </div>
    {flash}
    {body}
  </div>
  <script>
    async function nbCopy(text) {{
      try {{
        await navigator.clipboard.writeText(text);
      }} catch (e) {{
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
      }}
      const toast = document.getElementById('nb-toast');
      if (toast) {{
        toast.textContent = '已复制';
        toast.classList.add('show');
        window.clearTimeout(window.__nbToastTimer);
        window.__nbToastTimer = window.setTimeout(() => toast.classList.remove('show'), 1200);
      }}
    }}
  </script>
  <div id="nb-toast" class="toast" aria-live="polite"></div>
</body>
</html>"""

        def _render_dashboard(self, *, msg: str = "", err: str = "") -> None:
            cfg = self._load_config()
            channels_data = cfg.channels.model_dump()
            channel_names = ["telegram", "discord", "feishu", "dingtalk", "qq", "slack", "whatsapp", "email", "mochat"]
            enabled_channels = [name for name in channel_names if bool((channels_data.get(name) or {}).get("enabled"))]
            endpoint_names = sorted(cfg.providers.endpoints.keys())
            mcp_servers = cfg.tools.mcp_servers or {}
            skills_rows = _collect_skill_rows(cfg)
            unavailable_skills = [s for s in skills_rows if (not s["available"]) and (not s["disabled"])]
            body = f"""
<div class="grid cols-3">
  <section class="card"><h2>当前模型</h2><div class="kpi mono">{escape(cfg.agents.defaults.model)}</div><div class="muted">默认会话模型（聊天内可用 /model 切换）</div></section>
  <section class="card"><h2>命名端点</h2><div class="kpi">{len(endpoint_names)}</div><div class="muted">{escape(', '.join(endpoint_names[:6]) or '未配置')}</div></section>
  <section class="card"><h2>启用渠道</h2><div class="kpi">{len(enabled_channels)}</div><div class="muted">{escape(', '.join(enabled_channels) or '无')}</div></section>
</div>
<div class="split" style="margin-top:14px">
  <section class="card">
    <h2>运行目录</h2>
    <table>
      <tr><th>Config</th><td><code>{escape(str(cfg_path))}</code></td></tr>
      <tr><th>Env 主文件</th><td><code>{escape(str(get_env_file()))}</code></td></tr>
      <tr><th>Env 目录</th><td><code>{escape(str(get_env_dir()))}</code></td></tr>
      <tr><th>全局技能目录</th><td><code>{escape(str(get_global_skills_path()))}</code></td></tr>
      <tr><th>工作区</th><td><code>{escape(str(cfg.workspace_path))}</code></td></tr>
    </table>
    <div class="row" style="margin-top:10px">
      <a class="btn subtle" href="/endpoints">管理模型端点</a>
      <a class="btn subtle" href="/channels">管理聊天渠道</a>
      <a class="btn subtle" href="/extensions">管理 MCP / 技能</a>
    </div>
  </section>
  <section class="card">
    <h2>快速诊断（轻量）</h2>
    <ul class="list small">
      <li>web_search provider: <code>{escape(cfg.tools.web.search.provider)}</code></li>
      <li>MCP servers: {len(mcp_servers)} configured / {len(cfg.tools.mcp_enabled_servers or [])} allowlisted</li>
      <li>aliases: {len(cfg.tools.aliases or {})}</li>
      <li>skills.disabled: {len(cfg.skills.disabled or [])}</li>
      <li>不可用技能（未禁用）: {len(unavailable_skills)}</li>
      <li>Claude Code tool: {"enabled" if cfg.tools.claude_code.enabled else "disabled"}</li>
    </ul>
    <div class="muted">更详细诊断仍建议用命令行 <code>nanobot doctor</code></div>
  </section>
</div>
"""
            self._send_html(200, self._page("Dashboard", body, tab="/", msg=msg, err=err))

        def _render_endpoints(self, *, msg: str = "", err: str = "") -> None:
            cfg = self._load_config()
            cards = []
            switch_rows: list[str] = []
            for name in sorted(cfg.providers.endpoints.keys()):
                ep = cfg.providers.endpoints[name]
                models_csv = ", ".join(ep.models or [])
                headers_json = _pretty_json(ep.extra_headers or {})
                if ep.models:
                    for model_name in ep.models[:8]:
                        cmd = f"/model {name}/{model_name}"
                        switch_rows.append(
                            f'<tr><td><code>{escape(name)}</code></td><td><code>{escape(model_name)}</code></td>'
                            f'<td><code>{escape(cmd)}</code></td>'
                            f'<td><button type="button" class="btn" data-copy="{escape(cmd)}" onclick="nbCopy(this.dataset.copy)">复制</button></td></tr>'
                        )
                else:
                    hint = f"{name}/<model-name>"
                    cmd = f"/model {hint}"
                    switch_rows.append(
                        f'<tr><td><code>{escape(name)}</code></td><td class="muted">（未限制）</td>'
                        f'<td><code>{escape(cmd)}</code></td>'
                        f'<td><button type="button" class="btn" data-copy="{escape(cmd)}" onclick="nbCopy(this.dataset.copy)">复制</button></td></tr>'
                    )
                options = "".join(
                    f'<option value="{t}" {"selected" if ep.type == t else ""}>{t}</option>' for t in _ENDPOINT_TYPES
                )
                cards.append(
                    f"""
<form method="post" class="endpoint-card">
  <input type="hidden" name="original_name" value="{escape(name)}">
  <div class="endpoint-head">
    <h3><code>{escape(name)}</code></h3>
    <div class="row">
      <button class="btn primary" type="submit" name="action" value="save_endpoint">保存</button>
      <button class="btn" type="submit" formaction="/endpoints" name="action" value="delete_endpoint" onclick="return confirm('删除端点 {escape(name)} ?');">删除</button>
    </div>
  </div>
  <div class="endpoint-fields">
    <div class="field"><label>名字（用于 /model endpoint/model）</label><input type="text" name="name" value="{escape(name)}"></div>
    <div class="field"><label>类型（协议/路由）</label><select name="type">{options}</select></div>
    <div class="field"><label>API Base（可用 ${'{'}ENV{'}'} 占位）</label><input type="text" name="api_base" value="{escape(ep.api_base or '')}"></div>
    <div class="field"><label>API Key（建议使用 env 占位）</label><input type="text" name="api_key" value="{escape(ep.api_key or '')}"></div>
    <div class="field full"><label>Models（逗号分隔；空=不限）</label><input type="text" name="models_csv" value="{escape(models_csv)}"></div>
    <div class="field full"><label>Extra Headers JSON</label><textarea name="extra_headers_json">{escape(headers_json)}</textarea></div>
    <div class="field"><label><input type="checkbox" name="enabled" {"checked" if ep.enabled else ""}> 启用该端点</label></div>
  </div>
</form>
"""
                )
            options = "".join(f'<option value="{t}">{t}</option>' for t in _ENDPOINT_TYPES)
            add_form = f"""
<form method="post" class="card">
  <h2>新增端点</h2>
  <input type="hidden" name="action" value="save_endpoint">
  <div class="endpoint-fields">
    <div class="field"><label>名字</label><input type="text" name="name" placeholder="myopen"></div>
    <div class="field"><label>类型</label><select name="type">{options}</select></div>
    <div class="field"><label>API Base</label><input type="text" name="api_base" placeholder="${'{'}MYOPEN_BASE{'}'}"></div>
    <div class="field"><label>API Key</label><input type="text" name="api_key" placeholder="${'{'}MYOPEN_KEY{'}'}"></div>
    <div class="field full"><label>Models（逗号分隔）</label><input type="text" name="models_csv" placeholder="qwen-max, deepseek-v3"></div>
    <div class="field full"><label>Extra Headers JSON</label><textarea name="extra_headers_json">{{}}</textarea></div>
    <div class="field"><label><input type="checkbox" name="enabled" checked> 启用</label></div>
  </div>
  <div class="row">
    <button class="btn primary" type="submit">新增端点</button>
  </div>
</form>
"""
            helper = f"""
<section class="card">
  <h2>默认模型</h2>
  <form method="post" class="row">
    <input type="hidden" name="action" value="set_default_model">
    <input type="text" name="default_model" value="{escape(cfg.agents.defaults.model)}" style="flex:1" placeholder="myopen/qwen-max">
    <button class="btn primary" type="submit">保存默认模型</button>
  </form>
  <div class="muted">聊天里仍可用 <code>/model endpoint/model</code> 会话级切换。</div>
</section>
<section class="card" style="margin-top:14px">
  <h2>聊天内快捷切换命令</h2>
  <table>
    <tr><th>Endpoint</th><th>Model</th><th>/model 命令</th><th></th></tr>
    {''.join(switch_rows) or '<tr><td colspan="4" class="muted">先新增 endpoint；配置 models 后这里会生成快捷命令。</td></tr>'}
  </table>
  <div class="muted">这些命令可直接发给机器人会话（TG/Discord/其他渠道）进行会话级模型切换。</div>
</section>
"""
            body = f'<div class="grid">{helper}{add_form}{"".join(cards) or "<section class=\"card\"><div class=\"muted\">还没有命名端点。先新增一个即可。</div></section>"}</div>'
            self._send_html(200, self._page("Models & APIs", body, tab="/endpoints", msg=msg, err=err))

        def _render_channels(self, *, msg: str = "", err: str = "") -> None:
            cfg = self._load_config()
            channels_json = _pretty_json(cfg.channels.model_dump(by_alias=True))
            channels_dump = cfg.channels.model_dump()
            cards = []
            for name in ["telegram", "discord", "feishu", "dingtalk", "qq", "slack", "whatsapp", "email", "mochat"]:
                item = channels_dump.get(name) or {}
                enabled = bool(item.get("enabled"))
                keys = []
                for k, v in item.items():
                    if isinstance(v, (str, int, bool)) and k not in {"enabled"}:
                        if any(x in k.lower() for x in ("token", "secret", "password", "key")):
                            shown = _mask_secret(str(v))
                        else:
                            shown = str(v)
                        if shown:
                            keys.append(f"{k}={shown}")
                    if len(keys) >= 3:
                        break
                cards.append(
                    f"""
<tr>
  <td><code>{name}</code></td>
  <td>{'<span class="pill ok">enabled</span>' if enabled else '<span class="pill off">disabled</span>'}</td>
  <td class="small">{escape('; '.join(keys) or '-')}</td>
</tr>
"""
                )
            body = f"""
<div class="split">
  <section class="card">
    <h2>多渠道概览</h2>
    <table>
      <tr><th>Channel</th><th>Status</th><th>配置片段（脱敏）</th></tr>
      {''.join(cards)}
    </table>
    <div class="muted" style="margin-top:8px">本页使用 JSON 编辑器覆盖全部 channels 配置，适合一次管理多个渠道。</div>
  </section>
  <section class="card">
    <h2>通道行为（全局）</h2>
    <ul class="list small">
      <li>sendProgress: {'on' if cfg.channels.send_progress else 'off'}</li>
      <li>sendToolHints: {'on' if cfg.channels.send_tool_hints else 'off'}（建议关闭）</li>
      <li>主用 TG 时建议：保持 <code>sendToolHints=false</code></li>
    </ul>
    <div class="muted">修改渠道 token/secret 后通常需要重启 gateway 才会生效。</div>
  </section>
</div>
<form method="post" class="card" style="margin-top:14px">
  <h2>Channels JSON 编辑器</h2>
  <div class="field"><label>完整 channels 配置（支持 ${'{'}ENV_VAR{'}'} 占位）</label>
    <textarea name="channels_json" style="min-height:420px">{escape(channels_json)}</textarea>
  </div>
  <div class="row">
    <button class="btn primary" type="submit" name="action" value="save_channels_json">保存 Channels</button>
  </div>
</form>
"""
            self._send_html(200, self._page("Channels", body, tab="/channels", msg=msg, err=err))

        def _render_extensions(self, *, msg: str = "", err: str = "") -> None:
            cfg = self._load_config()
            tools_json = _pretty_json(cfg.tools.model_dump(by_alias=True))
            skills_json = _pretty_json(cfg.skills.model_dump(by_alias=True))
            mcp_rows = []
            for name in sorted(cfg.tools.mcp_servers.keys()):
                srv = cfg.tools.mcp_servers[name]
                target = srv.url or f"{srv.command} {' '.join(srv.args or [])}".strip()
                enabled = (
                    (not cfg.tools.mcp_enabled_servers)
                    or (name in cfg.tools.mcp_enabled_servers)
                ) and (name not in (cfg.tools.mcp_disabled_servers or []))
                mcp_rows.append(
                    f"<tr><td><code>{escape(name)}</code></td><td>{'<span class=\"pill ok\">enabled</span>' if enabled else '<span class=\"pill off\">filtered</span>'}</td><td class='mono'>{escape(target)}</td></tr>"
                )
            skill_rows = _collect_skill_rows(cfg)
            skill_table = []
            for s in skill_rows:
                badge = '<span class="pill ok">available</span>' if s["available"] else '<span class="pill off">missing deps</span>'
                if s["disabled"]:
                    badge = '<span class="pill">disabled</span>'
                skill_table.append(
                    f"""
<tr>
  <td><input type="checkbox" name="enabled_skill" value="{escape(s['name'])}" {"checked" if not s['disabled'] else ""}></td>
  <td><code>{escape(s['name'])}</code></td>
  <td>{escape(s['source'])}</td>
  <td>{badge}</td>
  <td class="small">{escape(s['requires'])}</td>
</tr>
"""
                )
            body = f"""
<div class="grid cols-2">
  <section class="card">
    <h2>MCP 概览</h2>
    <table>
      <tr><th>Server</th><th>Status</th><th>Target</th></tr>
      {''.join(mcp_rows) or '<tr><td colspan="3" class="muted">未配置 MCP servers</td></tr>'}
    </table>
    <form method="post" class="row" style="margin-top:10px">
      <button class="btn warn" type="submit" name="action" value="apply_recommended_mcp">应用推荐（Exa + docloader）</button>
    </form>
    <div class="muted">这会写入 Exa 搜索、docloader 文档解析、以及常用 aliases，不会清空你的其他配置。</div>
  </section>
  <section class="card">
    <h2>技能管理（启用/禁用）</h2>
    <form method="post">
      <input type="hidden" name="action" value="save_skills_enabled">
      <table>
        <tr><th></th><th>Skill</th><th>Source</th><th>Status</th><th>Requires</th></tr>
        {''.join(skill_table) or '<tr><td colspan="5" class="muted">无技能</td></tr>'}
      </table>
      <div class="row" style="margin-top:10px"><button class="btn primary" type="submit">保存技能启用状态</button></div>
    </form>
  </section>
</div>
<div class="grid cols-2" style="margin-top:14px">
  <form method="post" class="card">
    <h2>Tools JSON 编辑器</h2>
    <input type="hidden" name="action" value="save_tools_json">
    <textarea name="tools_json" style="min-height:420px">{escape(tools_json)}</textarea>
    <div class="row" style="margin-top:10px"><button class="btn primary" type="submit">保存 Tools</button></div>
  </form>
  <form method="post" class="card">
    <h2>Skills JSON 编辑器</h2>
    <input type="hidden" name="action" value="save_skills_json">
    <textarea name="skills_json" style="min-height:420px">{escape(skills_json)}</textarea>
    <div class="row" style="margin-top:10px"><button class="btn primary" type="submit">保存 Skills</button></div>
  </form>
</div>
"""
            self._send_html(200, self._page("MCP & Skills", body, tab="/extensions", msg=msg, err=err))

        def _render_media(self, *, msg: str = "", err: str = "") -> None:
            rows = _list_media_rows()
            media_dir = get_media_dir()
            table_rows = []
            for r in rows[:300]:
                size_kb = f"{r['size']/1024:.1f} KB"
                from datetime import datetime
                mtime = datetime.fromtimestamp(r["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
                table_rows.append(
                    f"""
<tr>
  <td><input type="checkbox" name="selected_name" value="{escape(r['name'])}"></td>
  <td><code>{escape(r['display_name'])}</code><div class="muted mono">{escape(r['name'])}</div></td>
  <td>{escape(size_kb)}</td>
  <td class="small">{escape(mtime)}</td>
  <td class="mono small">{escape(r['path'])}</td>
  <td>
    <button class="btn" type="submit" name="action" value="delete_one:{escape(r['name'])}" onclick="return confirm('删除该文件?');">删除</button>
  </td>
</tr>
"""
                )
            body = f"""
<div class="grid cols-2">
  <section class="card">
    <h2>媒体目录</h2>
    <table>
      <tr><th>目录</th><td><code>{escape(str(media_dir))}</code></td></tr>
      <tr><th>文件数</th><td>{len(rows)}</td></tr>
    </table>
    <div class="muted" style="margin-top:8px">这里是聊天渠道（TG/Discord/Feishu 等）下载的附件目录。建议先查看再删除。</div>
  </section>
  <section class="card">
    <h2>聊天内清理命令（推荐）</h2>
    <ul class="list small">
      <li>先列出：<code>media_files(action=&quot;list&quot;)</code></li>
      <li>再删除：<code>media_files(action=&quot;delete&quot;, names=[...])</code></li>
      <li>如果 TG 文件名看起来像随机串，请查看 <code>displayName</code>（已尽量保留原文件名）</li>
    </ul>
  </section>
</div>
<form method="post" class="card" style="margin-top:14px">
  <h2>媒体文件列表 / 删除</h2>
  <div class="row" style="margin-bottom:10px">
    <button class="btn warn" type="submit" name="action" value="delete_selected" onclick="return confirm('删除选中的文件?');">删除选中项</button>
    <button class="btn subtle" type="submit" name="action" value="refresh">刷新</button>
  </div>
  <table>
    <tr><th></th><th>显示名 / 文件名</th><th>大小</th><th>修改时间</th><th>路径</th><th></th></tr>
    {''.join(table_rows) or '<tr><td colspan="6" class="muted">媒体目录为空</td></tr>'}
  </table>
</form>
"""
            self._send_html(200, self._page("Media", body, tab="/media", msg=msg, err=err))

        def _handle_post_endpoints(self, form: dict[str, list[str]]) -> None:
            cfg = self._load_config()
            action = self._form_str(form, "action")
            if action == "set_default_model":
                model = self._form_str(form, "default_model").strip()
                if not model:
                    raise ValueError("default_model 不能为空")
                cfg.agents.defaults.model = model
                self._save_config(cfg)
                self._redirect("/endpoints", msg="默认模型已保存")
                return

            if action == "delete_endpoint":
                original_name = self._form_str(form, "original_name") or self._form_str(form, "name")
                name = original_name.strip()
                if not name:
                    raise ValueError("缺少端点名称")
                if name in cfg.providers.endpoints:
                    del cfg.providers.endpoints[name]
                    self._save_config(cfg)
                    self._redirect("/endpoints", msg=f"已删除端点: {name}")
                    return
                raise ValueError(f"端点不存在: {name}")

            if action != "save_endpoint":
                raise ValueError("Unsupported endpoints action")

            original_name = self._form_str(form, "original_name").strip()
            name = self._form_str(form, "name").strip()
            if not name:
                raise ValueError("端点名称不能为空")

            cfg_type = (self._form_str(form, "type") or "openai_compatible").strip().lower().replace("-", "_")
            api_base = self._form_str(form, "api_base").strip() or None
            api_key = self._form_str(form, "api_key").strip()
            models = _parse_csv(self._form_str(form, "models_csv"))
            headers = _safe_json_object(self._form_str(form, "extra_headers_json", "{}"), "extra_headers")
            ep = EndpointProviderConfig(
                type=cfg_type,
                api_base=api_base,
                api_key=api_key,
                extra_headers=headers or None,
                models=models,
                enabled=self._form_bool(form, "enabled"),
            )

            if original_name and original_name != name and original_name in cfg.providers.endpoints:
                del cfg.providers.endpoints[original_name]
            cfg.providers.endpoints[name] = ep
            self._save_config(cfg)
            self._redirect("/endpoints", msg=f"端点已保存: {name}")

        def _handle_post_channels(self, form: dict[str, list[str]]) -> None:
            cfg = self._load_config()
            action = self._form_str(form, "action")
            if action != "save_channels_json":
                raise ValueError("Unsupported channels action")
            raw = self._form_str(form, "channels_json")
            data = _safe_json_object(raw, "channels")
            cfg.channels = ChannelsConfig.model_validate(data)
            self._save_config(cfg)
            self._redirect("/channels", msg="Channels 配置已保存（如改了 token/secret，请重启 gateway）")

        def _handle_post_extensions(self, form: dict[str, list[str]]) -> None:
            cfg = self._load_config()
            action = self._form_str(form, "action")

            if action == "apply_recommended_mcp":
                _apply_recommended_tool_defaults(cfg)
                self._save_config(cfg)
                self._redirect("/extensions", msg="已写入推荐 MCP/aliases（Exa + docloader）")
                return

            if action == "save_tools_json":
                data = _safe_json_object(self._form_str(form, "tools_json"), "tools")
                cfg.tools = ToolsConfig.model_validate(data)
                self._save_config(cfg)
                self._redirect("/extensions", msg="Tools 配置已保存")
                return

            if action == "save_skills_json":
                data = _safe_json_object(self._form_str(form, "skills_json"), "skills")
                cfg.skills = SkillsConfig.model_validate(data)
                self._save_config(cfg)
                self._redirect("/extensions", msg="Skills 配置已保存")
                return

            if action == "save_skills_enabled":
                enabled_skills = {s.strip() for s in form.get("enabled_skill", []) if s.strip()}
                rows = _collect_skill_rows(cfg)
                all_known = [row["name"] for row in rows]
                cfg.skills.disabled = [name for name in all_known if name not in enabled_skills]
                self._save_config(cfg)
                self._redirect("/extensions", msg="技能启用状态已保存")
                return

            raise ValueError("Unsupported extensions action")

        def _handle_post_media(self, form: dict[str, list[str]]) -> None:
            action = self._form_str(form, "action")
            media_dir = get_media_dir().resolve()
            if action == "refresh":
                self._redirect("/media", msg="已刷新媒体列表")
                return

            names: list[str] = []
            if action == "delete_selected":
                names = [n.strip() for n in form.get("selected_name", []) if n.strip()]
            elif action.startswith("delete_one:"):
                names = [action.split(":", 1)[1].strip()]
            else:
                raise ValueError("Unsupported media action")

            if not names:
                raise ValueError("请选择要删除的文件")

            deleted = 0
            missing = 0
            for name in names:
                if "/" in name or "\\" in name or name in {".", ".."}:
                    continue
                p = (media_dir / name).resolve()
                try:
                    p.relative_to(media_dir)
                except ValueError:
                    continue
                if not p.exists():
                    missing += 1
                    continue
                if not p.is_file():
                    continue
                p.unlink(missing_ok=True)
                deleted += 1
            self._redirect("/media", msg=f"已删除 {deleted} 个文件" + (f"，缺失 {missing} 个" if missing else ""))

    httpd = ThreadingHTTPServer((host, port), Handler)
    public_host = "127.0.0.1" if host == "0.0.0.0" else host
    root_url = f"http://{public_host}:{port}/"
    access_url = f"http://{public_host}:{port}{path_prefix}/"
    print(f"nanobot Web UI listening on {root_url}")
    print(f"Web UI access path (required): {path_prefix}/")
    print(f"Open Web UI at: {access_url}")
    print(f"Path token file: {token_path}")
    if host not in {"127.0.0.1", "localhost"}:
        print("Warning: Web UI is not bound to localhost. Keep the path token secret and prefer a trusted network/reverse proxy.")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(access_url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Web UI...")
    finally:
        httpd.server_close()
