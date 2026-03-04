"""Minimal local web UI for managing lunaeclaw config."""

from __future__ import annotations

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

from lunaeclaw.app.gateway.control import (
    get_gateway_runtime_state_path as _get_gateway_runtime_state_path,
)
from lunaeclaw.app.webui import post_actions as _post_actions
from lunaeclaw.app.webui import views as _views
from lunaeclaw.app.webui.diagnostics import (
    collect_channel_runtime_issues as _collect_channel_runtime_issues_impl,
)
from lunaeclaw.app.webui.diagnostics import (
    collect_tool_policy_diagnostics as _collect_tool_policy_diagnostics_impl,
)
from lunaeclaw.app.webui.handlers import dispatch_post_route as _dispatch_post_route
from lunaeclaw.app.webui.i18n import (
    UI_LANGUAGE_CHOICES as _UI_LANGUAGE_CHOICES,
)
from lunaeclaw.app.webui.i18n import (
    normalize_ui_lang as _normalize_ui_lang,
)
from lunaeclaw.app.webui.i18n import (
    tr as _tr,
)
from lunaeclaw.app.webui.i18n import (
    ui_text as _ui_text,
)
from lunaeclaw.app.webui.icons import icon_svg
from lunaeclaw.app.webui.layout import render_page_shell as _render_page_shell
from lunaeclaw.app.webui.routes import dispatch_get_route as _dispatch_get_route
from lunaeclaw.app.webui.services import (
    configure_runtime_trend_store as _configure_runtime_trend_store,
)
from lunaeclaw.app.webui.services import (
    evaluate_gateway_runtime_status as _evaluate_gateway_runtime_status,
)
from lunaeclaw.app.webui.services import (
    runtime_trend_persist_hours_from_env as _runtime_trend_persist_hours_from_env,
)
from lunaeclaw.platform.config.loader import get_config_path, load_config, save_config
from lunaeclaw.platform.config.schema import Config


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
    """Start the local lunaeclaw web UI."""
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
    trend_persist_hours = _runtime_trend_persist_hours_from_env()
    _configure_runtime_trend_store(cfg_path.parent, persist_hours=trend_persist_hours)

    def _gateway_runtime_status() -> tuple[bool, str, str]:
        return _evaluate_gateway_runtime_status(cfg_path)

    class Handler(BaseHTTPRequestHandler):
        server_version = "lunaeclaw-webui/0.1"
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
            if route_path in {"/", "/chat", "/endpoints", "/channels", "/mcp", "/skills", "/extensions", "/media"}:
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
                target = route_path if route_path in {"/chat", "/endpoints", "/channels", "/mcp", "/skills", "/extensions", "/media"} else "/"
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
                ("/", _ui_text(self._ui_lang, "tab_dashboard"), "dashboard"),
                ("/chat", _ui_text(self._ui_lang, "tab_chat"), "chat"),
                ("/endpoints", _ui_text(self._ui_lang, "tab_models"), "model"),
                ("/channels", _ui_text(self._ui_lang, "tab_channels"), "channels"),
                ("/mcp", _ui_text(self._ui_lang, "tab_mcp"), "mcp"),
                ("/skills", _ui_text(self._ui_lang, "tab_skills"), "skills"),
                ("/media", _ui_text(self._ui_lang, "tab_media"), "media"),
            ]
            links = []
            for href, label, icon in items:
                active = "active" if tab == href else ""
                links.append(
                    f'<a class="nav-item {active}" href="{self._url_with_lang(href)}">{icon_svg(icon)}<span>{escape(label)}</span></a>'
                )
            return "".join(links)

        def _page(self, title: str, body: str, *, tab: str, msg: str = "", err: str = "") -> str:
            flash = ""
            if msg:
                flash += f'<div class="flash ok">{escape(msg)}</div>'
            if err:
                flash += f'<div class="flash err">{escape(err)}</div>'
            lang_label = _ui_text(self._ui_lang, "ui_lang")
            theme_label = _ui_text(self._ui_lang, "ui_theme")
            lang_options_html = "".join(
                f'<option value="{escape(code)}" {"selected" if self._ui_lang == code else ""}>{escape(label)}</option>'
                for code, label in _UI_LANGUAGE_CHOICES
            )
            theme_options_html = (
                f'<option value="auto">{escape(_ui_text(self._ui_lang, "theme_auto"))}</option>'
                f'<option value="light">{escape(_ui_text(self._ui_lang, "theme_light"))}</option>'
                f'<option value="dark">{escape(_ui_text(self._ui_lang, "theme_dark"))}</option>'
            )
            subtitle = _ui_text(self._ui_lang, "subtitle").format(host=escape(host), port=port)
            copied_label = _ui_text(self._ui_lang, "copied")
            return _render_page_shell(
                title=title,
                body=body,
                subtitle=subtitle,
                nav_html=self._nav(tab),
                flash_html=flash,
                ui_lang=self._ui_lang,
                lang_label=lang_label,
                lang_options_html=lang_options_html,
                theme_label=theme_label,
                theme_options_html=theme_options_html,
                copied_label=copied_label,
            )

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

        def _render_chat(self, *, msg: str = "", err: str = "") -> None:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            session_id = (params.get("session") or ["default"])[0]
            _views.render_chat(self, msg=msg, err=err, session_id=session_id)

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

        def _handle_post_chat(self, form: dict[str, list[str]]) -> None:
            _post_actions.handle_post_chat(self, form)

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
    print(f"LunaeClaw Control Hub listening on {root_url}")
    print(f"Web UI access path (required): {path_prefix}/")
    print(f"Open Web UI at: {access_url}")
    if trend_persist_hours > 0:
        print(f"Web UI trend persistence: enabled ({trend_persist_hours}h window)")
    else:
        print("Web UI trend persistence: disabled (memory-only)")
    print(f"Path token file: {token_path}")
    print(f"Gateway state file: {gateway_state_path}")
    _ready, _reason_en, _reason_zh = _gateway_runtime_status()
    if _ready:
        print("Gateway runtime check: OK (same data dir, alive)")
    else:
        print(f"Gateway runtime check: NOT READY ({_reason_en})")
        print("Tip: start gateway with the same LUNAECLAW_DATA_DIR/config directory.")
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
