"""Minimal local web UI for managing nanobot config."""

from __future__ import annotations

import os
import re
import secrets
import threading
import urllib.error
import urllib.request
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
from nanobot.utils.helpers import (
    get_env_dir,
    get_env_file,
    get_exports_dir,
    get_global_skills_path,
    get_media_dir,
)
from nanobot.utils.budget import (
    collect_runtime_budget_alerts,
    estimate_tokens_from_chars as _estimate_tokens_from_chars,
    read_host_resource_snapshot as _read_host_resource_snapshot,
)
from nanobot.webui.catalog import (
    MCP_LIBRARY as _MCP_LIBRARY,
    SKILL_LIBRARY as _SKILL_LIBRARY,
    evaluate_mcp_library_health,
    evaluate_skill_library_health,
    find_mcp_library_entry,
    install_skill_from_library,
    library_text as _library_text,
)
from nanobot.webui.common import (
    _CHANNEL_QUICK_SPECS,
    _ENDPOINT_TYPES,
    _ENV_PLACEHOLDER_RE,
    _MAX_SKILL_IMPORT_BYTES,
    _MEDIA_PAGE_SIZE,
    _REPLY_LANGUAGE_CODES,
    _apply_recommended_tool_defaults,
    _check_default_model_ref,
    _collect_skill_rows,
    _derive_env_prefix_from_placeholders,
    _fetch_public_json,
    _get_nested_attr,
    _is_env_placeholder,
    _list_media_rows,
    _list_store_rows,
    _mask_secret,
    _mask_sensitive_url,
    _merge_unique,
    _parse_csv,
    _pretty_json,
    _safe_int,
    _safe_json_object,
    _sanitize_env_key,
    _set_nested_attr,
)
from nanobot.webui.handlers import dispatch_post_route as _dispatch_post_route
from nanobot.webui import post_actions as _post_actions
from nanobot.webui import views as _views
from nanobot.webui.i18n import (
    UI_LANGUAGE_CHOICES as _UI_LANGUAGE_CHOICES,
    normalize_ui_lang as _normalize_ui_lang,
    reply_language_label as _reply_language_label,
    tr as _tr,
    ui_text as _ui_text,
)
from nanobot.webui.routes import dispatch_get_route as _dispatch_get_route
from nanobot.webui.services import (
    evaluate_gateway_runtime_status as _evaluate_gateway_runtime_status,
    safe_positive_int as _safe_positive_int,
)
from nanobot.webui.diagnostics import (
    collect_channel_runtime_issues as _collect_channel_runtime_issues_impl,
    collect_config_migration_hints,
    collect_tool_policy_diagnostics as _collect_tool_policy_diagnostics_impl,
)
from nanobot.gateway.control import get_gateway_runtime_state_path as _get_gateway_runtime_state_path


def _collect_channel_runtime_issues(raw_cfg: Config, resolved_cfg: Config, ui_lang: str) -> list[str]:
    return _collect_channel_runtime_issues_impl(raw_cfg, resolved_cfg, ui_lang=ui_lang)


def _collect_tool_policy_diagnostics(cfg: Config, ui_lang: str) -> list[str]:
    return _collect_tool_policy_diagnostics_impl(cfg, ui_lang=ui_lang)


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
    gateway_state_path = _get_gateway_runtime_state_path(cfg_path)

    def _gateway_runtime_status() -> tuple[bool, str, str]:
        return _evaluate_gateway_runtime_status(cfg_path)

    class Handler(BaseHTTPRequestHandler):
        server_version = "nanobot-webui/0.1"
        _ui_lang = "en"

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return  # keep CLI clean

        def do_HEAD(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path or "/"
            params = parse_qs(parsed.query)
            self._ui_lang = _normalize_ui_lang((params.get("lang") or ["en"])[0])
            if path in {"/healthz", f"{path_prefix}/healthz"}:
                self._send_text(200, "ok", head_only=True)
                return
            route_path = self._route_path(path)
            if route_path is None:
                self._send_text(404, "Not Found", head_only=True)
                return
            if route_path in {"/", "/endpoints", "/channels", "/mcp", "/skills", "/extensions", "/media"}:
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
            self._ui_lang = _normalize_ui_lang((params.get("lang") or ["en"])[0])
            msg = (params.get("msg") or [""])[0]
            err = (params.get("err") or [""])[0]
            try:
                handled = _dispatch_get_route(
                    self,
                    route_path,
                    params=params,
                    msg=msg,
                    err=err,
                )
                if not handled:
                    self._send_html(
                        404,
                        self._page(
                            _ui_text(self._ui_lang, "not_found"),
                            f"<p>{escape(_tr(self._ui_lang, 'Not Found', '未找到页面'))}</p>",
                            tab="",
                        ),
                    )
            except Exception as e:  # keep UI resilient
                self._send_html(500, self._page(_ui_text(self._ui_lang, "error"), f"<pre>{escape(str(e))}</pre>", tab=""))

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            route_path = self._route_path(parsed.path or "/")
            if route_path is None:
                self._send_text(404, "Not Found")
                return
            form = self._read_form()
            self._ui_lang = _normalize_ui_lang(self._form_str(form, "ui_lang", self._ui_lang))
            try:
                handled = _dispatch_post_route(self, route_path, form)
                if not handled:
                    self._redirect("/", err=_ui_text(self._ui_lang, "unsupported_action"))
            except Exception as e:
                target = route_path if route_path in {"/endpoints", "/channels", "/mcp", "/skills", "/extensions", "/media"} else "/"
                self._redirect(target, err=str(e))

        def _load_config(self) -> Config:
            return load_config(cfg_path, apply_profiles=False, resolve_env=False)

        def _save_config(self, config: Config) -> None:
            save_config(config, cfg_path)

        def _gateway_reload_ready(self) -> tuple[bool, str]:
            ready, reason_en, reason_zh = _gateway_runtime_status()
            if ready:
                return True, ""
            return False, reason_zh if self._ui_lang == "zh-CN" else reason_en

        def _append_apply_status(self, base_msg_en: str, base_msg_zh: str) -> str:
            ready, reason = self._gateway_reload_ready()
            if ready:
                return base_msg_zh if self._ui_lang == "zh-CN" else base_msg_en
            if self._ui_lang == "zh-CN":
                return f"{base_msg_zh}（未自动生效：{reason}）"
            return f"{base_msg_en} (not auto-applied: {reason})"

        def _read_form(self) -> dict[str, list[str]]:
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length).decode("utf-8", errors="replace")
            return parse_qs(raw, keep_blank_values=True)

        def _form_str(self, form: dict[str, list[str]], key: str, default: str = "") -> str:
            return (form.get(key) or [default])[0]

        def _form_bool(self, form: dict[str, list[str]], key: str) -> bool:
            return key in form and (self._form_str(form, key).lower() not in {"0", "false", "off"})

        def _url_with_lang(self, path: str) -> str:
            sep = "&" if "?" in path else "?"
            return f"{path}{sep}lang={self._ui_lang}"

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

        def _redirect(self, path: str, *, msg: str = "", err: str = "", ui_lang: str | None = None) -> None:
            params: dict[str, str] = {}
            if msg:
                params["msg"] = msg
            if err:
                params["err"] = err
            params["lang"] = _normalize_ui_lang(ui_lang or self._ui_lang)
            url = f"{path_prefix}{path}" if path_prefix and path.startswith("/") else path
            if params:
                sep = "&" if "?" in url else "?"
                url = f"{url}{sep}{urlencode(params)}"
            self.send_response(303)
            self.send_header("Location", url)
            self.end_headers()

        def _nav(self, tab: str) -> str:
            items = [
                ("/", _ui_text(self._ui_lang, "tab_dashboard")),
                ("/endpoints", _ui_text(self._ui_lang, "tab_models")),
                ("/channels", _ui_text(self._ui_lang, "tab_channels")),
                ("/mcp", _ui_text(self._ui_lang, "tab_mcp")),
                ("/skills", _ui_text(self._ui_lang, "tab_skills")),
                ("/media", _ui_text(self._ui_lang, "tab_media")),
            ]
            links = []
            for href, label in items:
                active = "active" if tab == href else ""
                links.append(f'<a class="nav-item {active}" href="{self._url_with_lang(href)}">{escape(label)}</a>')
            return "".join(links)

        def _page(self, title: str, body: str, *, tab: str, msg: str = "", err: str = "") -> str:
            flash = ""
            if msg:
                flash += f'<div class="flash ok">{escape(msg)}</div>'
            if err:
                flash += f'<div class="flash err">{escape(err)}</div>'
            external_host = "127.0.0.1" if host == "0.0.0.0" else host
            full_access_url = f"http://{external_host}:{port}{path_prefix}/"
            lang_label = _ui_text(self._ui_lang, "ui_lang")
            lang_options_html = "".join(
                f'<option value="{escape(code)}" {"selected" if self._ui_lang == code else ""}>{escape(label)}</option>'
                for code, label in _UI_LANGUAGE_CHOICES
            )
            subtitle = _ui_text(self._ui_lang, "subtitle").format(host=escape(host), port=port)
            copied_label = _ui_text(self._ui_lang, "copied")
            return f"""<!doctype html>
<html lang="{escape(self._ui_lang)}">
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
    .icon-btn {{ display:inline-flex; align-items:center; gap:6px; }}
    .btn.primary {{ background: var(--accent); color: #fff; border-color: var(--accent); }}
    .btn.warn {{ background: var(--accent-2); color: #fff; border-color: var(--accent-2); }}
    .btn.subtle {{ background: rgba(255,255,255,.55); }}
    .lang-switch {{
      display:inline-flex; align-items:center; gap:8px; border:1px solid var(--line);
      border-radius:10px; padding:6px 8px; background:rgba(255,255,255,.55);
    }}
    .lang-icon-btn {{
      width:28px; height:28px; display:inline-flex; align-items:center; justify-content:center;
      border:1px solid var(--line); border-radius:8px; background:#fff;
      font-size:14px; line-height:1;
    }}
    .lang-select {{
      border:none; background:transparent; padding:0 2px; min-width:120px;
      font: inherit; color: var(--ink);
    }}
    .lang-select:focus {{ outline:none; }}
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
        <p>{subtitle}</p>
      </div>
      <div style="display:grid; gap:8px;">
        <div class="row" style="justify-content:flex-end">
          <span class="muted">{lang_label}</span>
          <div class="lang-switch" title="{lang_label}">
            <span class="lang-icon-btn" aria-hidden="true">🌐</span>
            <select id="nb-lang-picker" class="lang-select" aria-label="{lang_label}">
              {lang_options_html}
            </select>
          </div>
        </div>
        <nav class="nav">{self._nav(tab)}</nav>
      </div>
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
        toast.textContent = '{escape(copied_label)}';
        toast.classList.add('show');
        window.clearTimeout(window.__nbToastTimer);
        window.__nbToastTimer = window.setTimeout(() => toast.classList.remove('show'), 1200);
      }}
    }}
    function nbSelectAll(form, checked) {{
      if (!form) return;
      for (const box of form.querySelectorAll('input[name=\"selected_name\"]')) {{
        box.checked = !!checked;
      }}
    }}
    (function bindLangPicker() {{
      const picker = document.getElementById('nb-lang-picker');
      if (!picker) return;
      picker.addEventListener('change', () => {{
        const u = new URL(window.location.href);
        u.searchParams.set('lang', picker.value);
        window.location.href = u.pathname + u.search;
      }});
    }})();
    (function bindUiLang() {{
      const uiLang = "{escape(self._ui_lang)}";
      for (const form of document.querySelectorAll('form')) {{
        if (!form.querySelector('input[name="ui_lang"]')) {{
          const hidden = document.createElement('input');
          hidden.type = 'hidden';
          hidden.name = 'ui_lang';
          hidden.value = uiLang;
          form.appendChild(hidden);
        }}
      }}
      for (const a of document.querySelectorAll('a[href^="/"]')) {{
        try {{
          const u = new URL(a.getAttribute('href'), window.location.origin);
          if (!u.searchParams.get('lang')) {{
            u.searchParams.set('lang', uiLang);
            a.setAttribute('href', u.pathname + u.search);
          }}
        }} catch (e) {{}}
      }}
    }})();
  </script>
  <div id="nb-toast" class="toast" aria-live="polite"></div>
</body>
</html>"""

        def _render_dashboard(self, *, msg: str = "", err: str = "") -> None:
            _views.render_dashboard(
                self,
                cfg_path=cfg_path,
                gateway_state_path=gateway_state_path,
                gateway_runtime_status=_gateway_runtime_status,
                collect_channel_runtime_issues=_collect_channel_runtime_issues,
                msg=msg,
                err=err,
            )

        def _render_endpoints(self, *, msg: str = "", err: str = "") -> None:
            _views.render_endpoints(self, msg=msg, err=err)

        def _render_channels(self, *, msg: str = "", err: str = "") -> None:
            _views.render_channels(
                self,
                cfg_path=cfg_path,
                gateway_runtime_status=_gateway_runtime_status,
                msg=msg,
                err=err,
            )

        def _render_mcp(self, *, msg: str = "", err: str = "") -> None:
            _views.render_mcp(
                self,
                collect_tool_policy_diagnostics=_collect_tool_policy_diagnostics,
                msg=msg,
                err=err,
            )

        def _render_skills(self, *, msg: str = "", err: str = "") -> None:
            _views.render_skills(self, msg=msg, err=err)

        def _render_media(
            self,
            *,
            msg: str = "",
            err: str = "",
            media_page: int = 1,
            exports_page: int = 1,
        ) -> None:
            _views.render_media(self, msg=msg, err=err, media_page=media_page, exports_page=exports_page)

        def _handle_post_endpoints(self, form: dict[str, list[str]]) -> None:
            _post_actions.handle_post_endpoints(self, form, cfg_path=cfg_path)

        def _handle_post_channels(self, form: dict[str, list[str]]) -> None:
            _post_actions.handle_post_channels(self, form)

        def _handle_post_mcp(self, form: dict[str, list[str]]) -> None:
            _post_actions.handle_post_mcp(self, form)

        def _handle_post_skills(self, form: dict[str, list[str]]) -> None:
            _post_actions.handle_post_skills(self, form)

        def _handle_post_media(self, form: dict[str, list[str]]) -> None:
            _post_actions.handle_post_media(self, form)

    httpd = ThreadingHTTPServer((host, port), Handler)
    public_host = "127.0.0.1" if host == "0.0.0.0" else host
    root_url = f"http://{public_host}:{port}/"
    access_url = f"http://{public_host}:{port}{path_prefix}/"
    print(f"nanobot Web UI listening on {root_url}")
    print(f"Web UI access path (required): {path_prefix}/")
    print(f"Open Web UI at: {access_url}")
    print(f"Path token file: {token_path}")
    print(f"Gateway state file: {gateway_state_path}")
    _ready, _reason_en, _reason_zh = _gateway_runtime_status()
    if _ready:
        print("Gateway runtime check: OK (same data dir, alive)")
    else:
        print(f"Gateway runtime check: NOT READY ({_reason_en})")
        print("Tip: start gateway with the same NANOBOT_DATA_DIR/config directory.")
    if host not in {"127.0.0.1", "localhost"}:
        print(_ui_text("en", "warn_not_localhost"))
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(access_url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{_ui_text('en', 'stopping_webui')}")
    finally:
        httpd.server_close()
