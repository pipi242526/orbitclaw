"""Minimal local web UI for managing nanobot config."""

from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import threading
import urllib.error
import urllib.request
import webbrowser
from ipaddress import ip_address
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
from nanobot.webui.catalog import (
    MCP_LIBRARY as _MCP_LIBRARY,
    SKILL_LIBRARY as _SKILL_LIBRARY,
    evaluate_mcp_library_health,
    evaluate_skill_library_health,
    find_mcp_library_entry,
    install_skill_from_library,
)
from nanobot.webui.diagnostics import (
    collect_channel_runtime_issues as _collect_channel_runtime_issues_impl,
    collect_config_migration_hints,
    collect_tool_policy_diagnostics as _collect_tool_policy_diagnostics_impl,
)


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

_REPLY_LANGUAGE_OPTIONS = [
    ("auto", "auto (跟随用户消息)"),
    ("zh-CN", "zh-CN (简体中文)"),
    ("en", "en (English)"),
    ("ja", "ja (日本語)"),
    ("ko", "ko (한국어)"),
    ("fr", "fr (Français)"),
    ("de", "de (Deutsch)"),
    ("es", "es (Español)"),
]

_MAX_SKILL_IMPORT_BYTES = 512 * 1024
_MAX_REMOTE_JSON_BYTES = 1024 * 1024

_CHANNEL_QUICK_SPECS: list[dict[str, Any]] = [
    {
        "id": "telegram",
        "title_en": "Telegram",
        "title_zh": "Telegram",
        "env_prefix": "TELEGRAM",
        "allow_field": "allow_from",
        "allow_env_prefix": "TELEGRAM_ALLOW_FROM",
        "fields": [
            {"path": "token", "label_en": "Bot Token", "label_zh": "Bot Token", "env_suffix": "BOT_TOKEN", "required": True, "secret": True},
            {"path": "proxy", "label_en": "Proxy URL", "label_zh": "代理 URL", "env_suffix": None, "required": False, "secret": False},
        ],
    },
    {
        "id": "discord",
        "title_en": "Discord",
        "title_zh": "Discord",
        "env_prefix": "DISCORD",
        "allow_field": "allow_from",
        "allow_env_prefix": "DISCORD_ALLOW_FROM",
        "fields": [
            {"path": "token", "label_en": "Bot Token", "label_zh": "Bot Token", "env_suffix": "BOT_TOKEN", "required": True, "secret": True},
        ],
    },
    {
        "id": "feishu",
        "title_en": "Feishu/Lark",
        "title_zh": "飞书/Lark",
        "env_prefix": "FEISHU",
        "allow_field": "allow_from",
        "allow_env_prefix": "FEISHU_ALLOW_FROM",
        "fields": [
            {"path": "app_id", "label_en": "App ID", "label_zh": "App ID", "env_suffix": "APP_ID", "required": True, "secret": False},
            {"path": "app_secret", "label_en": "App Secret", "label_zh": "App Secret", "env_suffix": "APP_SECRET", "required": True, "secret": True},
        ],
    },
    {
        "id": "dingtalk",
        "title_en": "DingTalk",
        "title_zh": "钉钉",
        "env_prefix": "DINGTALK",
        "allow_field": "allow_from",
        "allow_env_prefix": "DINGTALK_ALLOW_FROM",
        "fields": [
            {"path": "client_id", "label_en": "Client ID", "label_zh": "Client ID", "env_suffix": "CLIENT_ID", "required": True, "secret": False},
            {"path": "client_secret", "label_en": "Client Secret", "label_zh": "Client Secret", "env_suffix": "CLIENT_SECRET", "required": True, "secret": True},
        ],
    },
    {
        "id": "qq",
        "title_en": "QQ",
        "title_zh": "QQ",
        "env_prefix": "QQ",
        "allow_field": "allow_from",
        "allow_env_prefix": "QQ_ALLOW_FROM",
        "fields": [
            {"path": "app_id", "label_en": "App ID", "label_zh": "App ID", "env_suffix": "APP_ID", "required": True, "secret": False},
            {"path": "secret", "label_en": "App Secret", "label_zh": "App Secret", "env_suffix": "APP_SECRET", "required": True, "secret": True},
        ],
    },
    {
        "id": "slack",
        "title_en": "Slack",
        "title_zh": "Slack",
        "env_prefix": "SLACK",
        "allow_field": "group_allow_from",
        "allow_env_prefix": "SLACK_GROUP_ALLOW_FROM",
        "fields": [
            {"path": "bot_token", "label_en": "Bot Token", "label_zh": "Bot Token", "env_suffix": "BOT_TOKEN", "required": True, "secret": True},
            {"path": "app_token", "label_en": "App Token", "label_zh": "App Token", "env_suffix": "APP_TOKEN", "required": True, "secret": True},
        ],
    },
    {
        "id": "whatsapp",
        "title_en": "WhatsApp",
        "title_zh": "WhatsApp",
        "env_prefix": "WHATSAPP",
        "allow_field": "allow_from",
        "allow_env_prefix": "WHATSAPP_ALLOW_FROM",
        "fields": [
            {"path": "bridge_url", "label_en": "Bridge URL", "label_zh": "桥接 URL", "env_suffix": None, "required": False, "secret": False},
            {"path": "bridge_token", "label_en": "Bridge Token", "label_zh": "桥接 Token", "env_suffix": "BRIDGE_TOKEN", "required": False, "secret": True},
        ],
    },
    {
        "id": "email",
        "title_en": "Email",
        "title_zh": "Email",
        "env_prefix": "EMAIL",
        "allow_field": "allow_from",
        "allow_env_prefix": "EMAIL_ALLOW_FROM",
        "fields": [
            {"path": "imap_host", "label_en": "IMAP Host", "label_zh": "IMAP 主机", "env_suffix": "IMAP_HOST", "required": False, "secret": False},
            {"path": "imap_username", "label_en": "IMAP Username", "label_zh": "IMAP 用户名", "env_suffix": "IMAP_USERNAME", "required": False, "secret": False},
            {"path": "imap_password", "label_en": "IMAP Password", "label_zh": "IMAP 密码", "env_suffix": "IMAP_PASSWORD", "required": False, "secret": True},
            {"path": "smtp_host", "label_en": "SMTP Host", "label_zh": "SMTP 主机", "env_suffix": "SMTP_HOST", "required": False, "secret": False},
            {"path": "smtp_username", "label_en": "SMTP Username", "label_zh": "SMTP 用户名", "env_suffix": "SMTP_USERNAME", "required": False, "secret": False},
            {"path": "smtp_password", "label_en": "SMTP Password", "label_zh": "SMTP 密码", "env_suffix": "SMTP_PASSWORD", "required": False, "secret": True},
            {"path": "from_address", "label_en": "From Address", "label_zh": "发件地址", "env_suffix": "FROM_ADDRESS", "required": False, "secret": False},
        ],
    },
    {
        "id": "mochat",
        "title_en": "Mochat",
        "title_zh": "Mochat",
        "env_prefix": "MOCHAT",
        "allow_field": "allow_from",
        "allow_env_prefix": "MOCHAT_ALLOW_FROM",
        "fields": [
            {"path": "base_url", "label_en": "Base URL", "label_zh": "基础 URL", "env_suffix": None, "required": False, "secret": False},
            {"path": "claw_token", "label_en": "Claw Token", "label_zh": "Claw Token", "env_suffix": "CLAW_TOKEN", "required": False, "secret": True},
            {"path": "agent_user_id", "label_en": "Agent User ID", "label_zh": "Agent 用户 ID", "env_suffix": "AGENT_USER_ID", "required": False, "secret": False},
        ],
    },
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
            url="https://mcp.exa.ai/mcp?tools=web_search_exa,get_code_context_exa&exaApiKey=${EXA_API_KEY}"
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


def _safe_int(raw: str, field_name: str, *, minimum: int = 0) -> int:
    try:
        value = int((raw or "").strip())
    except ValueError as e:
        raise ValueError(f"{field_name} must be an integer") from e
    if value < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return value


_ENV_PLACEHOLDER_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _is_env_placeholder(text: str) -> bool:
    return bool(_ENV_PLACEHOLDER_RE.match((text or "").strip()))


def _sanitize_env_key(raw: str, default: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", (raw or "").strip().upper())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned:
        return default
    if not re.match(r"^[A-Za-z_]", cleaned):
        return default
    return cleaned


def _get_nested_attr(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        cur = getattr(cur, part)
    return cur


def _set_nested_attr(obj: Any, path: str, value: Any) -> None:
    parts = path.split(".")
    cur = obj
    for part in parts[:-1]:
        cur = getattr(cur, part)
    setattr(cur, parts[-1], value)


def _read_host_resource_snapshot() -> dict[str, float | int | None]:
    out: dict[str, float | int | None] = {
        "load1": None,
        "load5": None,
        "load15": None,
        "mem_used_percent": None,
        "disk_used_percent": None,
    }
    try:
        load1, load5, load15 = os.getloadavg()
        out["load1"] = float(load1)
        out["load5"] = float(load5)
        out["load15"] = float(load15)
    except Exception:
        pass

    try:
        total = available = None
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) * 1024
        if total and available is not None and total > 0:
            used = max(0, total - available)
            out["mem_used_percent"] = (used / total) * 100.0
    except Exception:
        pass

    try:
        disk = shutil.disk_usage("/")
        if disk.total > 0:
            out["disk_used_percent"] = (disk.used / disk.total) * 100.0
    except Exception:
        pass
    return out


def _estimate_tokens_from_chars(chars: int) -> int:
    # Coarse default for mixed CJK+Latin content in prompts.
    return max(0, int(chars / 3))


def _derive_env_prefix_from_placeholders(values: list[str], default_prefix: str) -> str:
    for raw in values or []:
        m = _ENV_PLACEHOLDER_RE.match((raw or "").strip())
        if not m:
            continue
        key = m.group(1)
        if "_" in key:
            return key.rsplit("_", 1)[0]
    return default_prefix


def _collect_channel_runtime_issues(raw_cfg: Config, resolved_cfg: Config) -> list[str]:
    return _collect_channel_runtime_issues_impl(raw_cfg, resolved_cfg)


def _collect_tool_policy_diagnostics(cfg: Config) -> list[str]:
    return _collect_tool_policy_diagnostics_impl(cfg)


def _normalize_ui_lang(value: str | None) -> str:
    lang = (value or "en").strip().lower()
    return "zh-CN" if lang in {"zh", "zh-cn", "cn"} else "en"


def _mask_sensitive_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return raw
    return re.sub(
        r"(?i)(api[-_]?key|token|secret|password)=([^&]+)",
        lambda m: f"{m.group(1)}={_mask_secret(m.group(2))}",
        raw,
    )


def _is_private_or_local_host(hostname: str) -> bool:
    h = (hostname or "").strip().lower()
    if not h:
        return True
    if h in {"localhost", "127.0.0.1", "::1"} or h.endswith(".local"):
        return True
    try:
        infos = socket.getaddrinfo(h, None)
    except socket.gaierror:
        return True
    for info in infos:
        ip = info[4][0]
        try:
            obj = ip_address(ip)
        except ValueError:
            continue
        if obj.is_private or obj.is_loopback or obj.is_link_local or obj.is_reserved:
            return True
    return False


def _build_models_url(api_base: str) -> str:
    base = (api_base or "").strip().rstrip("/")
    if base.endswith("/models"):
        return base
    return f"{base}/models"


def _check_default_model_ref(config: Config, model_ref: str, *, probe_remote: bool = False) -> tuple[bool, str]:
    text = (model_ref or "").strip()
    if "/" not in text:
        return False, "default model must be in endpoint/model format"
    endpoint_name, model_name = text.split("/", 1)
    endpoint_name = endpoint_name.strip()
    model_name = model_name.strip()
    if not endpoint_name or not model_name:
        return False, "default model must be in endpoint/model format"

    ep = config.providers.endpoints.get(endpoint_name)
    if ep is None:
        return False, f"endpoint not found: {endpoint_name}"
    if not ep.enabled:
        return False, f"endpoint is disabled: {endpoint_name}"
    if ep.models:
        allowed = {str(x).strip() for x in ep.models if str(x).strip()}
        full_ref = f"{endpoint_name}/{model_name}"
        if model_name not in allowed and full_ref not in allowed:
            return False, f"model '{model_name}' is not listed in endpoint '{endpoint_name}'"

    if ep.type not in {"openai", "openai_compatible"}:
        return True, "ok (structural check)"
    if not probe_remote:
        return True, "ok (structural check)"
    if not ep.api_base:
        return False, f"endpoint '{endpoint_name}' has empty api_base"

    headers: dict[str, str] = {"Accept": "application/json", "User-Agent": "nanobot-webui/0.1"}
    if ep.api_key:
        headers["Authorization"] = f"Bearer {ep.api_key}"
    if ep.extra_headers:
        headers.update({str(k): str(v) for k, v in ep.extra_headers.items()})

    url = _build_models_url(ep.api_base)
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return False, f"probe failed for endpoint '{endpoint_name}': {e}"

    data = payload.get("data")
    if isinstance(data, list):
        ids = {str(item.get("id", "")).strip() for item in data if isinstance(item, dict)}
        ids.discard("")
        if ids and model_name not in ids:
            return False, f"model '{model_name}' not returned by {endpoint_name}/models"
    return True, "ok"


def _fetch_public_json(url: str, *, max_bytes: int = _MAX_REMOTE_JSON_BYTES) -> Any:
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https":
        raise ValueError("URL must use https://")
    if not parsed.hostname:
        raise ValueError("URL must include host")
    if _is_private_or_local_host(parsed.hostname):
        raise ValueError("URL host must be public")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "nanobot-webui/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            blob = resp.read(max_bytes + 1)
    except urllib.error.URLError as e:
        raise ValueError(f"failed to fetch URL: {e}") from e
    if len(blob) > max_bytes:
        raise ValueError("remote JSON is too large")
    try:
        return json.loads(blob.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid JSON: {e}") from e


_UI_TEXTS = {
    "en": {
        "tab_dashboard": "Dashboard",
        "tab_models": "Models & APIs",
        "tab_channels": "Channels",
        "tab_mcp": "MCP",
        "tab_skills": "Skills",
        "tab_media": "Media",
        "ui_lang": "Language",
        "not_found": "Not Found",
        "error": "Error",
    },
    "zh-CN": {
        "tab_dashboard": "仪表盘",
        "tab_models": "模型与接口",
        "tab_channels": "渠道",
        "tab_mcp": "MCP",
        "tab_skills": "技能",
        "tab_media": "媒体文件",
        "ui_lang": "语言",
        "not_found": "未找到页面",
        "error": "错误",
    },
}


def _ui_text(lang: str, key: str) -> str:
    return _UI_TEXTS.get(lang, _UI_TEXTS["en"]).get(key, key)


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


def _list_store_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not root.exists():
        return rows
    for p in sorted(root.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
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


def _list_media_rows() -> list[dict[str, Any]]:
    return _list_store_rows(get_media_dir())


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
                if route_path == "/":
                    self._render_dashboard(msg=msg, err=err)
                elif route_path == "/endpoints":
                    self._render_endpoints(msg=msg, err=err)
                elif route_path == "/channels":
                    self._render_channels(msg=msg, err=err)
                elif route_path == "/extensions":
                    self._redirect("/mcp", msg=msg, err=err)
                elif route_path == "/mcp":
                    self._render_mcp(msg=msg, err=err)
                elif route_path == "/skills":
                    self._render_skills(msg=msg, err=err)
                elif route_path == "/media":
                    self._render_media(msg=msg, err=err)
                else:
                    self._send_html(404, self._page(_ui_text(self._ui_lang, "not_found"), "<p>Not Found</p>", tab=""))
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
                if route_path == "/endpoints":
                    self._handle_post_endpoints(form)
                    return
                if route_path == "/channels":
                    self._handle_post_channels(form)
                    return
                if route_path == "/mcp":
                    self._handle_post_mcp(form)
                    return
                if route_path == "/skills":
                    self._handle_post_skills(form)
                    return
                if route_path == "/extensions":
                    self._handle_post_mcp(form)
                    return
                if route_path == "/media":
                    self._handle_post_media(form)
                    return
                self._redirect("/", err="Unsupported action")
            except Exception as e:
                target = route_path if route_path in {"/endpoints", "/channels", "/mcp", "/skills", "/extensions", "/media"} else "/"
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
                url = f"{url}?{urlencode(params)}"
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
            subtitle = (
                f"Lightweight config console (Host: {escape(host)}:{port}) · Path-token protected"
                if self._ui_lang == "en"
                else f"轻量配置管理台（Host: {escape(host)}:{port}） · 使用路径密钥访问"
            )
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
        <p>{subtitle}</p>
      </div>
      <div style="display:grid; gap:8px;">
        <div class="row" style="justify-content:flex-end">
          <span class="muted">{lang_label}</span>
          <a class="btn subtle" href="{self._url_with_lang(tab or '/').replace('lang='+self._ui_lang, 'lang=en')}">EN</a>
          <a class="btn subtle" href="{self._url_with_lang(tab or '/').replace('lang='+self._ui_lang, 'lang=zh-CN')}">中文</a>
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
        toast.textContent = '{'Copied' if self._ui_lang == 'en' else '已复制'}';
        toast.classList.add('show');
        window.clearTimeout(window.__nbToastTimer);
        window.__nbToastTimer = window.setTimeout(() => toast.classList.remove('show'), 1200);
      }}
    }}
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
            cfg = self._load_config()
            cfg_resolved = load_config(cfg_path, apply_profiles=False, resolve_env=True)
            zh = self._ui_lang == "zh-CN"
            t = (lambda en, zh_cn: zh_cn if zh else en)
            channels_data = cfg.channels.model_dump()
            channel_names = [str(x["id"]) for x in _CHANNEL_QUICK_SPECS]
            enabled_channels = [name for name in channel_names if bool((channels_data.get(name) or {}).get("enabled"))]
            endpoint_names = sorted(cfg.providers.endpoints.keys())
            mcp_servers = cfg.tools.mcp_servers or {}
            skills_rows = _collect_skill_rows(cfg)
            unavailable_skills = [s for s in skills_rows if (not s["available"]) and (not s["disabled"])]
            media_count = len(_list_media_rows())
            export_count = len(_list_store_rows(get_exports_dir(cfg.tools.files_hub.exports_dir)))
            default_model_ok, default_model_reason = _check_default_model_ref(
                cfg_resolved,
                cfg.agents.defaults.model,
            )
            channel_issues = _collect_channel_runtime_issues(cfg, cfg_resolved)
            config_hints = collect_config_migration_hints(cfg_path)
            issues = [*channel_issues]
            if not default_model_ok:
                issues.append(f"default model: {default_model_reason}")
            for hint in config_hints:
                issues.append(f"config: {hint}")
            for ep_name, ep_cfg in cfg.providers.endpoints.items():
                for model_ref in ep_cfg.models or []:
                    text = str(model_ref).strip()
                    if text.startswith(f"{ep_name}/"):
                        issues.append(f"endpoint `{ep_name}` model allowlist contains endpoint prefix: `{text}`")
                        break
            if cfg.tools.web.search.provider == "exa_mcp":
                exa_server = cfg_resolved.tools.mcp_servers.get("exa")
                exa_url = (exa_server.url or "") if exa_server else ""
                if exa_server and re.search(r"exaApiKey=(&|$)", exa_url):
                    issues.append("exa_mcp: EXA_API_KEY not resolved")
            health_score = max(0, 100 - len(issues) * 15)
            ready_channel_count = max(0, len(enabled_channels) - len({x.split(":", 1)[0] for x in channel_issues}))
            snapshot = _read_host_resource_snapshot()
            load1 = snapshot.get("load1")
            mem_used_percent = snapshot.get("mem_used_percent")
            disk_used_percent = snapshot.get("disk_used_percent")

            history_chars = int(cfg.agents.defaults.max_history_chars)
            memory_chars = int(cfg.agents.defaults.max_memory_context_chars)
            background_chars = int(cfg.agents.defaults.max_background_context_chars)
            total_chars_budget = max(0, history_chars + memory_chars + background_chars)
            total_tokens_budget = _estimate_tokens_from_chars(total_chars_budget)
            inline_image_mb = max(0.0, cfg.agents.defaults.max_inline_image_bytes / 1024 / 1024)

            action_rows = []
            for item in issues[:6]:
                if item.startswith("default model:"):
                    action_rows.append(
                        f"<li>{escape(item)} · <a class='mono' href='/endpoints'>{t('fix in Models & APIs', '去模型与接口修复')}</a></li>"
                    )
                elif item.startswith("endpoint `"):
                    action_rows.append(
                        f"<li>{escape(item)} · <a class='mono' href='/endpoints'>{t('open endpoint and resave models', '打开端点后重新保存 models')}</a></li>"
                    )
                elif "exa_mcp" in item:
                    action_rows.append(
                        f"<li>{escape(item)} · <a class='mono' href='/mcp'>{t('fix in MCP page', '去 MCP 页面修复')}</a></li>"
                    )
                elif item.startswith("config:"):
                    action_rows.append(
                        f"<li>{escape(item)} · <a class='mono' href='/'>{t('review config migration hints and resave related page', '查看配置迁移提示后到对应页面重存')}</a></li>"
                    )
                else:
                    action_rows.append(
                        f"<li>{escape(item)} · <a class='mono' href='/channels'>{t('fix in Channels page', '去渠道页面修复')}</a></li>"
                    )
            body = f"""
<div class="grid cols-3">
  <section class="card">
    <h2>{t("Health Score", "健康分")}</h2>
    <div class="kpi">{health_score}</div>
    <div class="muted">{t("Based on model/channels/MCP runtime checks", "基于模型/渠道/MCP 运行时检查")}</div>
  </section>
  <section class="card">
    <h2>{t("Channels Ready", "渠道就绪")}</h2>
    <div class="kpi">{ready_channel_count}/{len(enabled_channels)}</div>
    <div class="muted">{escape(', '.join(enabled_channels) or t('none enabled', '未启用'))}</div>
  </section>
  <section class="card">
    <h2>{t("Named Endpoints", "命名端点")}</h2>
    <div class="kpi">{len(endpoint_names)}</div>
    <div class="muted">{escape(', '.join(endpoint_names[:6]) or t('none', '未配置'))}</div>
  </section>
</div>
<div class="grid cols-2" style="margin-top:14px">
  <section class="card">
    <h2>{t("Resource Radar", "资源雷达")}</h2>
    <table>
      <tr><th>{t("CPU load(1m)", "CPU 负载(1m)")}</th><td>{escape(f"{load1:.2f}" if isinstance(load1, float) else "n/a")}</td></tr>
      <tr><th>{t("Memory used", "内存占用")}</th><td>{escape(f"{mem_used_percent:.1f}%" if isinstance(mem_used_percent, float) else "n/a")}</td></tr>
      <tr><th>{t("Disk used(/)", "磁盘占用(/)")}</th><td>{escape(f"{disk_used_percent:.1f}%" if isinstance(disk_used_percent, float) else "n/a")}</td></tr>
    </table>
    <div class="muted">
      {t("This is a lightweight runtime snapshot from the current host.", "这是当前主机的轻量运行快照。")}
    </div>
  </section>
  <section class="card">
    <h2>{t("Token Budget Radar", "Token 预算雷达")}</h2>
    <table>
      <tr><th>history</th><td>{history_chars} chars ≈ { _estimate_tokens_from_chars(history_chars) } tokens</td></tr>
      <tr><th>memory</th><td>{memory_chars} chars ≈ { _estimate_tokens_from_chars(memory_chars) } tokens</td></tr>
      <tr><th>background</th><td>{background_chars} chars ≈ { _estimate_tokens_from_chars(background_chars) } tokens</td></tr>
      <tr><th>{t("total context cap", "总上下文预算")}</th><td>{total_chars_budget} chars ≈ {total_tokens_budget} tokens</td></tr>
      <tr><th>{t("inline image cap", "内联图片上限")}</th><td>{inline_image_mb:.2f} MB</td></tr>
      <tr><th>{t("gc / cache", "gc / 缓存")}</th><td>gcEveryTurns={cfg.agents.defaults.gc_every_turns}, cache={cfg.agents.defaults.session_cache_max_entries}</td></tr>
    </table>
    <div class="muted">{t("Estimation uses ~1 token per 3 chars (mixed text).", "估算按约 1 token ≈ 3 chars（中英混合粗估）。")}</div>
  </section>
</div>
<div class="split" style="margin-top:14px">
  <section class="card">
    <h2>{t("Actionable Checks", "待处理检查项")}</h2>
    <ul class="list small">
      {''.join(action_rows) or f"<li>{t('No blocking issue found.', '未发现阻塞问题。')}</li>"}
    </ul>
    <div class="row" style="margin-top:10px">
      <a class="btn subtle" href="/channels">{t("Manage Channels", "管理聊天渠道")}</a>
      <a class="btn subtle" href="/endpoints">{t("Manage Models", "管理模型端点")}</a>
      <a class="btn subtle" href="/mcp">{t("Manage MCP", "管理 MCP")}</a>
    </div>
  </section>
  <section class="card">
    <h2>{t("Runtime Paths & Counters", "运行目录与计数")}</h2>
    <table>
      <tr><th>Config</th><td><code>{escape(str(cfg_path))}</code></td></tr>
      <tr><th>{t("Env main file", "Env 主文件")}</th><td><code>{escape(str(get_env_file()))}</code></td></tr>
      <tr><th>{t("Env directory", "Env 目录")}</th><td><code>{escape(str(get_env_dir()))}</code></td></tr>
      <tr><th>{t("Global skills", "全局技能目录")}</th><td><code>{escape(str(get_global_skills_path()))}</code></td></tr>
      <tr><th>{t("Workspace", "工作区")}</th><td><code>{escape(str(cfg.workspace_path))}</code></td></tr>
      <tr><th>{t("Media files", "媒体文件数")}</th><td>{media_count}</td></tr>
      <tr><th>{t("Export files", "导出文件数")}</th><td>{export_count}</td></tr>
      <tr><th>{t("Default model check", "默认模型检查")}</th><td>{'OK' if default_model_ok else 'FAIL'} ({escape(default_model_reason)})</td></tr>
      <tr><th>{t("Config migration hints", "配置迁移提示")}</th><td>{len(config_hints)}</td></tr>
      <tr><th>{t("Unavailable skills", "不可用技能")}</th><td>{len(unavailable_skills)}</td></tr>
      <tr><th>{t("MCP servers", "MCP 服务数")}</th><td>{len(mcp_servers)} ({len(cfg.tools.mcp_enabled_servers or [])} allowlisted)</td></tr>
    </table>
    <div class="muted">{t("For full diagnostics, run", "更详细诊断建议使用")} <code>nanobot doctor</code></div>
  </section>
</div>
"""
            self._send_html(200, self._page(t("Dashboard", "仪表盘"), body, tab="/", msg=msg, err=err))

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
            reply_lang_options_html = "".join(
                f'<option value="{escape(v)}" {"selected" if cfg.agents.defaults.reply_language == v else ""}>{escape(label)}</option>'
                for v, label in _REPLY_LANGUAGE_OPTIONS
            )
            fallback_lang_options_html = "".join(
                f'<option value="{escape(v)}" {"selected" if cfg.agents.defaults.auto_reply_fallback_language == v else ""}>{escape(label)}</option>'
                for v, label in _REPLY_LANGUAGE_OPTIONS
            )
            default_model_candidates: list[str] = []
            for ep_name in sorted(cfg.providers.endpoints.keys()):
                ep = cfg.providers.endpoints[ep_name]
                if not ep.enabled:
                    continue
                for model_name in ep.models or []:
                    ref = f"{ep_name}/{model_name}"
                    if ref not in default_model_candidates:
                        default_model_candidates.append(ref)
            if cfg.agents.defaults.model not in default_model_candidates:
                default_model_candidates.insert(0, cfg.agents.defaults.model)
            default_model_options = "".join(
                f'<option value="{escape(v)}" {"selected" if v == cfg.agents.defaults.model else ""}>{escape(v)}</option>'
                for v in default_model_candidates
            )

            helper = f"""
<section class="card">
  <h2>{"Default Model" if self._ui_lang == "en" else "默认模型"}</h2>
  <form method="post" class="row">
    <input type="hidden" name="action" value="set_default_model">
    <select name="default_model_select" style="min-width:380px; flex:1">
      {default_model_options}
    </select>
    <input type="text" name="default_model_custom" style="flex:1" placeholder="custom endpoint/model (optional)">
    <button class="btn primary" type="submit">{"Save Default Model" if self._ui_lang == "en" else "保存默认模型"}</button>
  </form>
  <div class="muted">{"Save action validates endpoint/model availability once before writing config." if self._ui_lang == "en" else "保存时会先做一次 endpoint/model 可用性检测，再写入配置。聊天里仍可用 /model 会话级切换。"}</div>
</section>
<section class="card" style="margin-top:14px">
  <h2>语言与搜索策略</h2>
  <form method="post">
    <input type="hidden" name="action" value="set_agent_preferences">
    <div class="endpoint-fields">
      <div class="field">
        <label>默认回复语言（最终回复）</label>
        <select name="reply_language">
          {reply_lang_options_html}
        </select>
      </div>
      <div class="field">
        <label>自动检测失败时的回退语言</label>
        <select name="auto_reply_fallback_language">
          {fallback_lang_options_html}
        </select>
      </div>
      <div class="field">
        <label><input type="checkbox" name="cross_lingual_search" {"checked" if cfg.agents.defaults.cross_lingual_search else ""}> 启用跨语言搜索提示（地区话题优先本地语言检索）</label>
        <div class="muted">例如中文问日本话题时，先用日语检索，再用中文总结。</div>
      </div>
    </div>
    <div class="row">
      <button class="btn primary" type="submit">保存语言/搜索策略</button>
    </div>
  </form>
  <div class="muted">这些设置会影响新请求的回复语言约束与搜索策略提示，不需要聊天命令。</div>
</section>
<section class="card" style="margin-top:14px">
  <h2>资源与上下文预算</h2>
  <form method="post">
    <input type="hidden" name="action" value="set_agent_runtime_budget">
    <div class="endpoint-fields">
      <div class="field"><label>history 字符预算（maxHistoryChars）</label><input type="number" min="0" name="max_history_chars" value="{cfg.agents.defaults.max_history_chars}"></div>
      <div class="field"><label>MEMORY 字符预算（maxMemoryContextChars）</label><input type="number" min="0" name="max_memory_context_chars" value="{cfg.agents.defaults.max_memory_context_chars}"></div>
      <div class="field"><label>背景字符预算（maxBackgroundContextChars）</label><input type="number" min="0" name="max_background_context_chars" value="{cfg.agents.defaults.max_background_context_chars}"></div>
      <div class="field"><label>内联图片大小上限（maxInlineImageBytes）</label><input type="number" min="0" name="max_inline_image_bytes" value="{cfg.agents.defaults.max_inline_image_bytes}"></div>
      <div class="field"><label><input type="checkbox" name="auto_compact_background" {"checked" if cfg.agents.defaults.auto_compact_background else ""}> 自动压缩背景信息（优先结构化压缩，再截断）</label></div>
      <div class="field"><label>系统提示缓存秒数（systemPromptCacheTtlSeconds）</label><input type="number" min="0" name="system_prompt_cache_ttl_seconds" value="{cfg.agents.defaults.system_prompt_cache_ttl_seconds}"></div>
      <div class="field"><label>会话缓存上限（sessionCacheMaxEntries）</label><input type="number" min="1" name="session_cache_max_entries" value="{cfg.agents.defaults.session_cache_max_entries}"></div>
      <div class="field"><label>GC 间隔轮次（gcEveryTurns，0=关闭）</label><input type="number" min="0" name="gc_every_turns" value="{cfg.agents.defaults.gc_every_turns}"></div>
    </div>
    <div class="row">
      <button class="btn primary" type="submit">保存资源策略</button>
    </div>
  </form>
  <div class="muted">建议先小步调整并观察响应质量与资源占用，再继续收紧预算。</div>
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
            cfg_resolved = load_config(cfg_path, apply_profiles=False, resolve_env=True)
            zh = self._ui_lang == "zh-CN"
            t = (lambda en, zh_cn: zh_cn if zh else en)
            channels_json = _pretty_json(cfg.channels.model_dump(by_alias=True))
            channels_dump = cfg.channels.model_dump()
            quick_options: list[str] = []
            default_quick_channel = ""
            quick_cards = []
            for spec in _CHANNEL_QUICK_SPECS:
                sid = str(spec["id"])
                raw_channel = getattr(cfg.channels, sid)
                if not default_quick_channel and bool(getattr(raw_channel, "enabled", False)):
                    default_quick_channel = sid
                quick_options.append(
                    f'<option value="{escape(sid)}">{escape(t(str(spec["title_en"]), str(spec["title_zh"])))}</option>'
                )
                resolved_channel = getattr(cfg_resolved.channels, sid)
                env_fields = [f for f in spec["fields"] if f.get("env_suffix")]
                auth_mode = "env_placeholders"
                for field in env_fields:
                    raw_val = str(_get_nested_attr(raw_channel, str(field["path"])) or "").strip()
                    if raw_val and not _is_env_placeholder(raw_val):
                        auth_mode = "plain"
                        break
                env_prefix = str(spec["env_prefix"])
                for field in env_fields:
                    raw_val = str(_get_nested_attr(raw_channel, str(field["path"])) or "").strip()
                    match = _ENV_PLACEHOLDER_RE.match(raw_val)
                    if not match:
                        continue
                    suffix = f"_{field['env_suffix']}"
                    key = match.group(1)
                    if key.endswith(suffix):
                        env_prefix = key[: -len(suffix)]
                        break

                allow_field = str(spec["allow_field"])
                allow_raw = list(_get_nested_attr(raw_channel, allow_field) or [])
                allow_resolved = list(_get_nested_attr(resolved_channel, allow_field) or [])
                allow_mode = "env_placeholders" if (allow_raw and all(_is_env_placeholder(x) for x in allow_raw)) else "plain"
                allow_prefix = _derive_env_prefix_from_placeholders(allow_raw, str(spec["allow_env_prefix"]))
                allow_csv = ", ".join(allow_resolved if (allow_mode == "env_placeholders" and allow_resolved) else allow_raw)

                field_rows = []
                for field in spec["fields"]:
                    path = str(field["path"])
                    input_name = f"ch_{sid}_{path.replace('.', '__')}"
                    raw_value = str(_get_nested_attr(raw_channel, path) or "")
                    display_value = raw_value
                    if not bool(field.get("secret")) and _is_env_placeholder(raw_value):
                        resolved_value = str(_get_nested_attr(resolved_channel, path) or "")
                        if resolved_value:
                            display_value = resolved_value
                    env_hint = ""
                    if field.get("env_suffix"):
                        env_hint = f"${{{env_prefix}_{field['env_suffix']}}}"
                    label_text = t(str(field["label_en"]), str(field["label_zh"]))
                    field_rows.append(
                        f"""
<div class="field">
  <label>{escape(label_text)}</label>
  <input type="text" name="{escape(input_name)}" value="{escape(display_value)}" placeholder="{escape(env_hint)}">
</div>
"""
                    )

                quick_cards.append(
                    f"""
<section class="card quick-channel-card" data-channel="{escape(sid)}" style="display:none;">
  <h3>{escape(t(str(spec['title_en']), str(spec['title_zh'])))}</h3>
  <div class="field"><label><input type="checkbox" name="ch_{escape(sid)}_enabled" {"checked" if bool(getattr(raw_channel, "enabled", False)) else ""}> {t("enabled", "启用")}</label></div>
  <div class="endpoint-fields">
    {''.join(field_rows)}
    <div class="field">
      <label>{t("credential storage", "凭据存储方式")}</label>
      <select name="ch_{escape(sid)}_auth_mode">
        <option value="env_placeholders" {"selected" if auth_mode == "env_placeholders" else ""}>{t("env placeholders (recommended)", "环境变量占位（推荐）")}</option>
        <option value="plain" {"selected" if auth_mode == "plain" else ""}>{t("plain text", "明文")}</option>
      </select>
    </div>
    <div class="field">
      <label>{t("credential env prefix", "凭据环境变量前缀")}</label>
      <input type="text" name="ch_{escape(sid)}_env_prefix" value="{escape(env_prefix)}" placeholder="{escape(str(spec['env_prefix']))}">
    </div>
    <div class="field full">
      <label>{t("allowFrom list (CSV)", "allowFrom 列表（逗号分隔）")}</label>
      <input type="text" name="ch_{escape(sid)}_allow_csv" value="{escape(allow_csv)}" placeholder="id1, id2">
    </div>
    <div class="field">
      <label>{t("allowFrom storage", "allowFrom 存储方式")}</label>
      <select name="ch_{escape(sid)}_allow_mode">
        <option value="env_placeholders" {"selected" if allow_mode == "env_placeholders" else ""}>{t("env placeholders (recommended)", "环境变量占位（推荐）")}</option>
        <option value="plain" {"selected" if allow_mode == "plain" else ""}>{t("plain text", "明文")}</option>
      </select>
    </div>
    <div class="field">
      <label>{t("allowFrom env prefix", "allowFrom 环境变量前缀")}</label>
      <input type="text" name="ch_{escape(sid)}_allow_env_prefix" value="{escape(allow_prefix)}" placeholder="{escape(str(spec['allow_env_prefix']))}">
    </div>
  </div>
</section>
"""
                )
            if not default_quick_channel and _CHANNEL_QUICK_SPECS:
                default_quick_channel = str(_CHANNEL_QUICK_SPECS[0]["id"])
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
<section class="card" style="margin-bottom:14px">
  <h2>{t("Multi-channel Quick Setup (Generic)", "多渠道通用快速配置")}</h2>
  <form method="post">
    <input type="hidden" name="action" value="save_channels_quick">
    <input type="hidden" name="quick_channel_id" id="quick_channel_id" value="{escape(default_quick_channel)}">
    <div class="field">
      <label>{t("Select channel", "选择渠道")}</label>
      <select id="quick_channel_picker">
        {''.join(quick_options)}
      </select>
    </div>
    <div>
      {''.join(quick_cards)}
    </div>
    <div class="row" style="margin-top:12px">
      <button class="btn primary" type="submit">{t("Save Selected Channel", "保存当前渠道配置")}</button>
      <span class="muted">{t("Choose one channel, edit fields below, then save.", "先选择渠道，再编辑下方配置并保存。")}</span>
    </div>
  </form>
  <script>
    (function bindQuickChannelPicker() {{
      const picker = document.getElementById('quick_channel_picker');
      const hidden = document.getElementById('quick_channel_id');
      const cards = Array.from(document.querySelectorAll('.quick-channel-card'));
      if (!picker || !hidden || cards.length === 0) return;
      function showSelected() {{
        const selected = picker.value;
        hidden.value = selected;
        for (const card of cards) {{
          const hit = card.getAttribute('data-channel') === selected;
          card.style.display = hit ? 'block' : 'none';
        }}
      }}
      picker.value = hidden.value || picker.options[0].value;
      picker.addEventListener('change', showSelected);
      showSelected();
    }})();
  </script>
</section>
<div class="split">
  <section class="card">
    <h2>{t("Channel Overview", "多渠道概览")}</h2>
    <table>
      <tr><th>Channel</th><th>Status</th><th>配置片段（脱敏）</th></tr>
      {''.join(cards)}
    </table>
    <div class="muted" style="margin-top:8px">{t("Use JSON editor below for full control of all channel fields.", "下方 JSON 编辑器可覆盖全部 channel 字段。")}</div>
  </section>
  <section class="card">
    <h2>{t("Global Channel Behavior", "通道行为（全局）")}</h2>
    <ul class="list small">
      <li>sendProgress: {'on' if cfg.channels.send_progress else 'off'}</li>
      <li>sendToolHints: {'on' if cfg.channels.send_tool_hints else 'off'}（建议关闭）</li>
      <li>{t("For TG-heavy usage, keep", "主用 TG 时建议保持")} <code>sendToolHints=false</code></li>
      <li>{t("allowFrom supports both plain IDs and env placeholders; team sharing usually prefers env placeholders.", "allowFrom 同时支持明文和环境变量占位；团队共享配置通常建议用 env 占位。")}</li>
    </ul>
    <div class="muted">{t("Restart gateway after changing channel token/secret.", "修改渠道 token/secret 后通常需要重启 gateway。")}</div>
  </section>
</div>
<form method="post" class="card" style="margin-top:14px">
  <h2>{t("Channels JSON Editor", "Channels JSON 编辑器")}</h2>
  <div class="field"><label>{t("Full channels config (supports ${ENV_VAR})", "完整 channels 配置（支持 ${ENV_VAR} 占位）")}</label>
    <textarea name="channels_json" style="min-height:420px">{escape(channels_json)}</textarea>
  </div>
  <div class="row">
    <button class="btn primary" type="submit" name="action" value="save_channels_json">{t("Save Channels JSON", "保存 Channels JSON")}</button>
  </div>
</form>
"""
            self._send_html(200, self._page(t("Channels", "渠道"), body, tab="/channels", msg=msg, err=err))

        def _render_mcp(self, *, msg: str = "", err: str = "") -> None:
            cfg = self._load_config()
            zh = self._ui_lang == "zh-CN"
            t = (lambda en, zh_cn: zh_cn if zh else en)
            mcp_rows = []
            for name in sorted(cfg.tools.mcp_servers.keys()):
                srv = cfg.tools.mcp_servers[name]
                target = _mask_sensitive_url(srv.url) if srv.url else f"{srv.command} {' '.join(srv.args or [])}".strip()
                enabled = (
                    (not cfg.tools.mcp_enabled_servers)
                    or (name in cfg.tools.mcp_enabled_servers)
                ) and (name not in (cfg.tools.mcp_disabled_servers or []))
                mcp_rows.append(
                    f"<tr><td><code>{escape(name)}</code></td><td>{'<span class=\"pill ok\">enabled</span>' if enabled else '<span class=\"pill off\">filtered</span>'}</td><td class='mono'>{escape(target)}</td></tr>"
                )
            diag_warnings = _collect_tool_policy_diagnostics(cfg)
            lib_rows = []
            for item in _MCP_LIBRARY:
                sid = item["id"]
                health = evaluate_mcp_library_health(cfg, item)
                health_label_map = {
                    "ready": t("ready", "就绪"),
                    "missing_env": t("missing env", "缺少环境变量"),
                    "missing_command": t("missing cmd", "缺少命令"),
                    "filtered": t("filtered", "已过滤"),
                    "not_installed": t("not installed", "未安装"),
                }
                health_label = health_label_map.get(health["status"], health["label"])
                health_class = "ok" if health["status"] == "ready" else "off"
                lib_rows.append(
                    f"""
<tr>
  <td><code>{escape(str(item['name']))}</code></td>
  <td class="small">{escape(str(item['desc']))}</td>
  <td><code>{escape(str(item['server_name']))}</code></td>
  <td><span class="pill {health_class}">{escape(str(health_label))}</span><div class="muted small">{escape(health['hint'])}</div></td>
  <td>
    <form method="post" class="row">
      <input type="hidden" name="action" value="install_mcp_library">
      <input type="hidden" name="library_id" value="{escape(sid)}">
      <label class="small"><input type="checkbox" name="overwrite_existing"> {t("overwrite", "覆盖已有")}</label>
      <button class="btn primary" type="submit">{t("Install", "安装")}</button>
    </form>
  </td>
</tr>
"""
                )
            body = f"""
<div class="grid cols-2">
  <section class="card">
    <h2>{t("MCP Servers", "MCP 服务")}</h2>
    <table>
      <tr><th>{t("Server", "服务")}</th><th>{t("Status", "状态")}</th><th>{t("Target (masked)", "目标（脱敏）")}</th></tr>
      {''.join(mcp_rows) or f'<tr><td colspan="3" class="muted">{t("No MCP server configured.", "尚未配置 MCP 服务。")}</td></tr>'}
    </table>
    <form method="post" class="row" style="margin-top:10px">
      <input type="hidden" name="action" value="apply_recommended_mcp">
      <button class="btn warn" type="submit">{t("Apply Recommended (Exa + Docloader)", "应用推荐（Exa + Docloader）")}</button>
    </form>
  </section>
  <section class="card">
    <h2>{t("Privacy", "隐私说明")}</h2>
    <ul class="list small">
      <li>{t("Do not place raw API keys directly in JSON where possible.", "建议不要在 JSON 里直接写明文 API Key。")}</li>
      <li>{t("Prefer", "建议使用")} <code>${'{'}ENV_VAR{'}'}</code> + <code>~/.nanobot/.env</code>.</li>
      <li>{t("This page masks sensitive query values in MCP URLs.", "本页会自动脱敏 MCP URL 中的敏感参数。")}</li>
    </ul>
  </section>
</div>
<section class="card" style="margin-top:14px">
  <h2>{t("MCP Library", "MCP 库")}</h2>
  <table>
    <tr><th>{t("Name", "名称")}</th><th>{t("Description", "说明")}</th><th>{t("Server Key", "服务键")}</th><th>{t("Health", "健康检查")}</th><th>{t("Action", "操作")}</th></tr>
    {''.join(lib_rows)}
  </table>
</section>
<section class="card" style="margin-top:14px">
  <h2>{t("Install From Manifest URL", "从清单 URL 安装")}</h2>
  <form method="post" class="endpoint-fields">
    <input type="hidden" name="action" value="install_mcp_from_manifest_url">
    <div class="field full">
      <label>{t("Manifest URL (raw JSON list)", "清单 URL（raw JSON 列表）")}</label>
      <input type="text" name="manifest_url" placeholder="https://raw.githubusercontent.com/.../mcp-library.json">
    </div>
    <div class="field">
      <label>{t("Entry ID", "条目 ID")}</label>
      <input type="text" name="entry_id" placeholder="exa">
    </div>
    <div class="field">
      <label><input type="checkbox" name="overwrite_existing"> {t("overwrite existing server", "覆盖已有同名服务")}</label>
    </div>
    <div class="field full">
      <button class="btn warn" type="submit">{t("Install Entry", "安装条目")}</button>
    </div>
  </form>
  <div class="muted">{t("Manifest format: [{id,name,server_name,config:{url|command,args,env}}]", "清单格式：[{id,name,server_name,config:{url|command,args,env}}]")}</div>
</section>
<section class="card" style="margin-top:14px">
  <h2>{t("Add Custom MCP Server", "添加自定义 MCP 服务")}</h2>
  <form method="post">
    <input type="hidden" name="action" value="save_custom_mcp">
    <div class="endpoint-fields">
      <div class="field"><label>{t("Server key", "服务键")}</label><input type="text" name="server_name" placeholder="myserver"></div>
      <div class="field"><label>{t("Mode", "模式")}</label>
        <select name="mode">
          <option value="url">{t("HTTP URL", "HTTP URL")}</option>
          <option value="stdio">{t("Stdio command", "标准输入输出命令")}</option>
        </select>
      </div>
      <div class="field full"><label>{t("URL (for HTTP mode)", "URL（HTTP 模式）")}</label><input type="text" name="url" placeholder="https://example.com/mcp"></div>
      <div class="field"><label>{t("Command (for stdio mode)", "命令（stdio 模式）")}</label><input type="text" name="command" placeholder="uvx"></div>
      <div class="field"><label>{t("Args (CSV, stdio mode)", "参数（CSV，stdio 模式）")}</label><input type="text" name="args_csv" placeholder="package@latest, --flag"></div>
      <div class="field full"><label>{t("Env JSON (optional)", "Env JSON（可选）")}</label><textarea name="env_json" style="min-height:120px">{{}}</textarea></div>
      <div class="field"><label><input type="checkbox" name="enable_now" checked> {t("add to enabled servers", "加入启用服务列表")}</label></div>
    </div>
    <div class="row"><button class="btn primary" type="submit">{t("Save MCP Server", "保存 MCP 服务")}</button></div>
  </form>
</section>
<section class="card" style="margin-top:14px">
  <h2>{t("Consistency Checks", "一致性检查")}</h2>
  <ul class="list small">
    {''.join(f'<li>{escape(item)}</li>' for item in diag_warnings) or f'<li>{t("No obvious conflict found.", "未发现明显冲突。")}</li>'}
  </ul>
</section>
"""
            self._send_html(200, self._page(t("MCP", "MCP"), body, tab="/mcp", msg=msg, err=err))

        def _render_skills(self, *, msg: str = "", err: str = "") -> None:
            cfg = self._load_config()
            zh = self._ui_lang == "zh-CN"
            t = (lambda en, zh_cn: zh_cn if zh else en)
            skill_rows = _collect_skill_rows(cfg)
            known_skills = {str(s["name"]) for s in skill_rows}
            rows_html = []
            for s in skill_rows:
                badge = (
                    f'<span class="pill ok">{t("available", "可用")}</span>'
                    if s["available"]
                    else f'<span class="pill off">{t("missing deps", "缺少依赖")}</span>'
                )
                if s["disabled"]:
                    badge = f'<span class="pill">{t("disabled", "已禁用")}</span>'
                rows_html.append(
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
            lib_rows = []
            for item in _SKILL_LIBRARY:
                name = str(item["name"])
                exists = name in known_skills
                health = evaluate_skill_library_health(cfg, item, skill_rows)
                health_label_map = {
                    "ready": t("ready", "就绪"),
                    "disabled": t("disabled", "已禁用"),
                    "missing_deps": t("missing deps", "缺少依赖"),
                    "not_installed": t("not installed", "未安装"),
                }
                health_label = health_label_map.get(health["status"], health["label"])
                health_class = "ok" if health["status"] == "ready" else "off"
                action_html = (
                    f"""
<form method="post" class="row">
  <input type="hidden" name="action" value="enable_skill_from_library">
  <input type="hidden" name="skill_name" value="{escape(name)}">
  <button class="btn" type="submit">{t("Enable", "启用")}</button>
</form>
"""
                    if exists
                    else f"""
<form method="post" class="row">
  <input type="hidden" name="action" value="install_skill_library">
  <input type="hidden" name="library_skill_id" value="{escape(str(item['id']))}">
  <button class="btn primary" type="submit">{t("Install", "安装")}</button>
</form>
"""
                )
                lib_rows.append(
                    f"""
<tr>
  <td><code>{escape(name)}</code></td>
  <td class="small">{escape(str(item['desc']))}</td>
  <td><span class="pill {health_class}">{escape(str(health_label))}</span><div class="muted small">{escape(health['hint'])}</div></td>
  <td>{action_html}</td>
</tr>
"""
                )
            skills_json = _pretty_json(cfg.skills.model_dump(by_alias=True))
            body = f"""
<div class="grid cols-2">
  <section class="card">
    <h2>{t("Skill Library (Local)", "技能库（本地）")}</h2>
    <form method="post">
      <input type="hidden" name="action" value="save_skills_enabled">
      <table>
        <tr><th></th><th>{t("Skill", "技能")}</th><th>{t("Source", "来源")}</th><th>{t("Status", "状态")}</th><th>{t("Requires", "依赖")}</th></tr>
        {''.join(rows_html) or f'<tr><td colspan="5" class="muted">{t("No skill found.", "未发现技能。")}</td></tr>'}
      </table>
      <div class="row" style="margin-top:10px"><button class="btn primary" type="submit">{t("Save Skill Selection", "保存技能选择")}</button></div>
    </form>
  </section>
  <section class="card">
    <h2>{t("Skill Notes", "技能说明")}</h2>
    <ul class="list small">
      <li>{t("Keep only skills you actually use to reduce startup checks and noise.", "只保留常用技能，可减少启动检查和日志噪音。")}</li>
      <li>{t("Missing-dependency skills can stay disabled by default.", "缺少依赖的技能建议默认禁用。")}</li>
      <li>{t("Use the URL import box below if you want to add third-party skills.", "需要三方技能时，可使用下方 URL 导入。")}</li>
    </ul>
  </section>
</div>
<section class="card" style="margin-top:14px">
  <h2>{t("Skill Library", "技能库")}</h2>
  <table>
    <tr><th>{t("Name", "名称")}</th><th>{t("Description", "说明")}</th><th>{t("Health", "健康检查")}</th><th>{t("Action", "操作")}</th></tr>
    {''.join(lib_rows)}
  </table>
</section>
<section class="card" style="margin-top:14px">
  <h2>{t("Import Skill From URL", "从 URL 导入技能")}</h2>
  <form method="post" class="endpoint-fields">
    <input type="hidden" name="action" value="import_skill_from_url">
    <div class="field"><label>{t("Skill name", "技能名")}</label><input type="text" name="skill_name" placeholder="my-skill"></div>
    <div class="field"><label>SKILL.md URL</label><input type="text" name="skill_url" placeholder="https://raw.githubusercontent.com/.../SKILL.md"></div>
    <div class="field full"><button class="btn warn" type="submit">{t("Import", "导入")}</button></div>
  </form>
</section>
<form method="post" class="card" style="margin-top:14px">
  <h2>{t("Skills JSON (Advanced)", "Skills JSON（高级）")}</h2>
  <input type="hidden" name="action" value="save_skills_json">
  <textarea name="skills_json" style="min-height:360px">{escape(skills_json)}</textarea>
  <div class="row" style="margin-top:10px"><button class="btn primary" type="submit">{t("Save Skills JSON", "保存 Skills JSON")}</button></div>
</form>
"""
            self._send_html(200, self._page(t("Skills", "技能"), body, tab="/skills", msg=msg, err=err))

        def _render_media(self, *, msg: str = "", err: str = "") -> None:
            cfg = self._load_config()
            configured_exports_dir = (cfg.tools.files_hub.exports_dir or "").strip()
            effective_exports_dir = get_exports_dir(configured_exports_dir)

            def _render_store_block(
                *,
                scope: str,
                title: str,
                desc: str,
                rows: list[dict[str, Any]],
                root_dir: Path,
            ) -> str:
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
                return f"""
<section class="card" style="margin-top:14px">
  <h2>{escape(title)}</h2>
  <table>
    <tr><th>目录</th><td><code>{escape(str(root_dir))}</code></td></tr>
    <tr><th>文件数</th><td>{len(rows)}</td></tr>
  </table>
  <div class="muted" style="margin-top:8px">{escape(desc)}</div>
  <form method="post" style="margin-top:14px">
    <input type="hidden" name="scope" value="{escape(scope)}">
    <div class="row" style="margin-bottom:10px">
      <button class="btn warn" type="submit" name="action" value="delete_selected" onclick="return confirm('删除选中的文件?');">删除选中项</button>
      <button class="btn subtle" type="submit" name="action" value="refresh">刷新</button>
    </div>
    <table>
      <tr><th></th><th>显示名 / 文件名</th><th>大小</th><th>修改时间</th><th>路径</th><th></th></tr>
      {''.join(table_rows) or '<tr><td colspan="6" class="muted">目录为空</td></tr>'}
    </table>
  </form>
</section>
"""

            media_rows = _list_media_rows()
            export_rows = _list_store_rows(effective_exports_dir)
            media_dir = get_media_dir()
            exports_dir = effective_exports_dir
            body = f"""
<div class="grid cols-2">
  <section class="card">
    <h2>文件处理总览</h2>
    <table>
      <tr><th>上传附件（media）</th><td>{len(media_rows)} 个</td></tr>
      <tr><th>生成输出（exports）</th><td>{len(export_rows)} 个</td></tr>
      <tr><th>路由建议</th><td><code>files_hub(scope=...)</code> 统一管理</td></tr>
    </table>
    <div class="muted" style="margin-top:8px">遵循“输入(media) / 处理(workspace) / 输出(exports)”分层，减少误删原件和工具重复。</div>
  </section>
  <section class="card">
    <h2>聊天内文件管理命令（推荐）</h2>
    <ul class="list small">
      <li>推荐：<code>files_hub(action=&quot;list&quot;, scope=&quot;media&quot;)</code></li>
      <li>删除：<code>files_hub(action=&quot;delete&quot;, scope=&quot;media&quot;, names=[...])</code></li>
      <li>导出目录：<code>files_hub(action=&quot;list&quot;, scope=&quot;exports&quot;)</code></li>
      <li>如果 TG 文件名看起来像随机串，请查看 <code>displayName</code>（新上传文件会尽量保留原文件名/后缀）</li>
    </ul>
  </section>
</div>
<form method="post" class="card" style="margin-top:14px">
  <h2>导出目录设置</h2>
  <div class="field">
    <label>tools.filesHub.exportsDir（留空=默认 <code>~/.nanobot/exports</code>）</label>
    <input name="exports_dir" value="{escape(configured_exports_dir)}" placeholder="例如：/data/nanobot-exports 或 exports">
  </div>
  <div class="row">
    <button class="btn primary" type="submit" name="action" value="save_exports_dir">保存导出目录</button>
    <button class="btn subtle" type="submit" name="action" value="save_exports_dir_default">恢复默认目录</button>
  </div>
</form>
{_render_store_block(
    scope="media",
    title="媒体目录（上传附件）",
    desc="这里是聊天渠道（TG/Discord/Feishu 等）下载的附件目录。建议先查看再删除。",
    rows=media_rows,
    root_dir=media_dir,
)}
{_render_store_block(
    scope="exports",
    title="导出目录（生成文件）",
    desc="这里建议存放机器人生成的结果文件（如 txt/docx/pdf/xlsx 等），便于统一下载和清理。",
    rows=export_rows,
    root_dir=exports_dir,
)}
"""
            self._send_html(200, self._page("Media", body, tab="/media", msg=msg, err=err))

        def _handle_post_endpoints(self, form: dict[str, list[str]]) -> None:
            cfg = self._load_config()
            action = self._form_str(form, "action")
            if action == "set_default_model":
                model = (
                    self._form_str(form, "default_model_custom").strip()
                    or self._form_str(form, "default_model_select").strip()
                    or self._form_str(form, "default_model").strip()
                )
                if not model:
                    raise ValueError("default_model 不能为空")
                ok, reason = _check_default_model_ref(
                    load_config(cfg_path, apply_profiles=False, resolve_env=True),
                    model,
                    probe_remote=True,
                )
                if not ok:
                    raise ValueError(f"默认模型检测失败: {reason}")
                cfg.agents.defaults.model = model
                self._save_config(cfg)
                self._redirect("/endpoints", msg=f"默认模型已保存（检测通过: {reason}）")
                return

            if action == "set_agent_preferences":
                reply_language = self._form_str(form, "reply_language", "auto").strip() or "auto"
                fallback_language = self._form_str(form, "auto_reply_fallback_language", "zh-CN").strip() or "zh-CN"
                cfg.agents.defaults.reply_language = reply_language
                cfg.agents.defaults.auto_reply_fallback_language = fallback_language
                cfg.agents.defaults.cross_lingual_search = self._form_bool(form, "cross_lingual_search")
                self._save_config(cfg)
                self._redirect("/endpoints", msg="语言与搜索策略已保存")
                return

            if action == "set_agent_runtime_budget":
                cfg.agents.defaults.max_history_chars = _safe_int(
                    self._form_str(form, "max_history_chars", str(cfg.agents.defaults.max_history_chars)),
                    "max_history_chars",
                    minimum=0,
                )
                cfg.agents.defaults.max_memory_context_chars = _safe_int(
                    self._form_str(form, "max_memory_context_chars", str(cfg.agents.defaults.max_memory_context_chars)),
                    "max_memory_context_chars",
                    minimum=0,
                )
                cfg.agents.defaults.max_background_context_chars = _safe_int(
                    self._form_str(
                        form,
                        "max_background_context_chars",
                        str(cfg.agents.defaults.max_background_context_chars),
                    ),
                    "max_background_context_chars",
                    minimum=0,
                )
                cfg.agents.defaults.max_inline_image_bytes = _safe_int(
                    self._form_str(form, "max_inline_image_bytes", str(cfg.agents.defaults.max_inline_image_bytes)),
                    "max_inline_image_bytes",
                    minimum=0,
                )
                cfg.agents.defaults.auto_compact_background = self._form_bool(form, "auto_compact_background")
                cfg.agents.defaults.system_prompt_cache_ttl_seconds = _safe_int(
                    self._form_str(
                        form,
                        "system_prompt_cache_ttl_seconds",
                        str(cfg.agents.defaults.system_prompt_cache_ttl_seconds),
                    ),
                    "system_prompt_cache_ttl_seconds",
                    minimum=0,
                )
                cfg.agents.defaults.session_cache_max_entries = _safe_int(
                    self._form_str(form, "session_cache_max_entries", str(cfg.agents.defaults.session_cache_max_entries)),
                    "session_cache_max_entries",
                    minimum=1,
                )
                cfg.agents.defaults.gc_every_turns = _safe_int(
                    self._form_str(form, "gc_every_turns", str(cfg.agents.defaults.gc_every_turns)),
                    "gc_every_turns",
                    minimum=0,
                )
                self._save_config(cfg)
                self._redirect("/endpoints", msg="资源策略已保存")
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
            normalized_models: list[str] = []
            for item in models:
                text = item.strip()
                if text.startswith(f"{name}/"):
                    text = text[len(name) + 1 :].strip()
                if text and text not in normalized_models:
                    normalized_models.append(text)
            headers = _safe_json_object(self._form_str(form, "extra_headers_json", "{}"), "extra_headers")
            ep = EndpointProviderConfig(
                type=cfg_type,
                api_base=api_base,
                api_key=api_key,
                extra_headers=headers or None,
                models=normalized_models,
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
            if action == "save_channels_quick":
                selected_channel = self._form_str(form, "quick_channel_id", "").strip().lower()
                selected_specs = [s for s in _CHANNEL_QUICK_SPECS if str(s["id"]).lower() == selected_channel]
                if not selected_specs:
                    raise ValueError("请选择一个有效渠道")
                for spec in selected_specs:
                    sid = str(spec["id"])
                    channel_obj = getattr(cfg.channels, sid)
                    setattr(channel_obj, "enabled", self._form_bool(form, f"ch_{sid}_enabled"))

                    auth_mode = self._form_str(form, f"ch_{sid}_auth_mode", "env_placeholders").strip()
                    env_prefix = _sanitize_env_key(
                        self._form_str(form, f"ch_{sid}_env_prefix", str(spec["env_prefix"])),
                        str(spec["env_prefix"]),
                    )
                    for field in spec["fields"]:
                        path = str(field["path"])
                        form_key = f"ch_{sid}_{path.replace('.', '__')}"
                        current_value = str(_get_nested_attr(channel_obj, path) or "")
                        submitted = self._form_str(form, form_key, "").strip()
                        if auth_mode == "env_placeholders" and field.get("env_suffix"):
                            next_value = f"${{{env_prefix}_{field['env_suffix']}}}"
                        else:
                            next_value = submitted if submitted != "" else current_value
                        _set_nested_attr(channel_obj, path, next_value)

                    allow_values = _parse_csv(self._form_str(form, f"ch_{sid}_allow_csv", ""))
                    allow_mode = self._form_str(form, f"ch_{sid}_allow_mode", "env_placeholders").strip()
                    allow_prefix = _sanitize_env_key(
                        self._form_str(form, f"ch_{sid}_allow_env_prefix", str(spec["allow_env_prefix"])),
                        str(spec["allow_env_prefix"]),
                    )
                    if allow_mode == "env_placeholders":
                        allow_from = [f"${{{allow_prefix}_{idx + 1}}}" for idx, _ in enumerate(allow_values)]
                    else:
                        allow_from = allow_values
                    _set_nested_attr(channel_obj, str(spec["allow_field"]), allow_from)
                    setattr(cfg.channels, sid, channel_obj)

                self._save_config(cfg)
                self._redirect("/channels", msg=f"渠道 `{selected_channel}` 配置已保存（如改 token/secret，请重启 gateway）")
                return

            if action == "save_channels_json":
                raw = self._form_str(form, "channels_json")
                data = _safe_json_object(raw, "channels")
                cfg.channels = ChannelsConfig.model_validate(data)
                self._save_config(cfg)
                self._redirect("/channels", msg="Channels 配置已保存（如改了 token/secret，请重启 gateway）")
                return

            raise ValueError("Unsupported channels action")

        def _handle_post_mcp(self, form: dict[str, list[str]]) -> None:
            cfg = self._load_config()
            action = self._form_str(form, "action")

            if action == "apply_recommended_mcp":
                _apply_recommended_tool_defaults(cfg)
                self._save_config(cfg)
                self._redirect("/mcp", msg="Recommended MCP defaults applied (Exa + Docloader).")
                return

            if action == "install_mcp_library":
                library_id = self._form_str(form, "library_id").strip()
                overwrite = self._form_bool(form, "overwrite_existing")
                item = find_mcp_library_entry(library_id)
                if not item:
                    raise ValueError(f"Unknown MCP library entry: {library_id}")
                name = str(item["server_name"])
                if name in cfg.tools.mcp_servers and not overwrite:
                    self._redirect("/mcp", err=f"MCP server '{name}' already exists. Enable overwrite to replace.")
                    return
                cfg.tools.mcp_servers[name] = item["config"]
                cfg.tools.mcp_enabled_servers = _merge_unique(cfg.tools.mcp_enabled_servers, [name])
                self._save_config(cfg)
                self._redirect("/mcp", msg=f"Installed MCP library entry: {name}")
                return

            if action == "install_mcp_from_manifest_url":
                manifest_url = self._form_str(form, "manifest_url").strip()
                entry_id = self._form_str(form, "entry_id").strip()
                overwrite = self._form_bool(form, "overwrite_existing")
                if not manifest_url:
                    raise ValueError("manifest_url is required")
                if not entry_id:
                    raise ValueError("entry_id is required")
                payload = _fetch_public_json(manifest_url)
                if not isinstance(payload, list):
                    raise ValueError("manifest JSON must be an array")
                selected = None
                for item in payload:
                    if isinstance(item, dict) and str(item.get("id", "")).strip() == entry_id:
                        selected = item
                        break
                if not selected:
                    raise ValueError(f"entry_id not found in manifest: {entry_id}")
                server_name = str(selected.get("server_name", "")).strip()
                config_obj = selected.get("config")
                if not server_name:
                    raise ValueError("manifest entry missing server_name")
                if not isinstance(config_obj, dict):
                    raise ValueError("manifest entry missing config object")
                if server_name in cfg.tools.mcp_servers and not overwrite:
                    self._redirect("/mcp", err=f"MCP server '{server_name}' already exists. Enable overwrite to replace.")
                    return
                cfg.tools.mcp_servers[server_name] = MCPServerConfig.model_validate(config_obj)
                cfg.tools.mcp_enabled_servers = _merge_unique(cfg.tools.mcp_enabled_servers, [server_name])
                self._save_config(cfg)
                self._redirect("/mcp", msg=f"Installed MCP from manifest: {server_name}")
                return

            if action == "save_custom_mcp":
                server_name = self._form_str(form, "server_name").strip()
                mode = self._form_str(form, "mode", "url").strip().lower()
                if not server_name:
                    raise ValueError("server_name is required")
                if mode == "url":
                    url = self._form_str(form, "url").strip()
                    if not url:
                        raise ValueError("url is required for HTTP mode")
                    cfg.tools.mcp_servers[server_name] = MCPServerConfig(url=url)
                elif mode == "stdio":
                    cmd = self._form_str(form, "command").strip()
                    if not cmd:
                        raise ValueError("command is required for stdio mode")
                    args = _parse_csv(self._form_str(form, "args_csv", ""))
                    env = _safe_json_object(self._form_str(form, "env_json", "{}"), "env_json")
                    cfg.tools.mcp_servers[server_name] = MCPServerConfig(
                        command=cmd,
                        args=args,
                        env={str(k): str(v) for k, v in env.items()},
                    )
                else:
                    raise ValueError("mode must be url or stdio")
                if self._form_bool(form, "enable_now"):
                    cfg.tools.mcp_enabled_servers = _merge_unique(cfg.tools.mcp_enabled_servers, [server_name])
                self._save_config(cfg)
                self._redirect("/mcp", msg=f"Saved MCP server: {server_name}")
                return

            if action == "save_tools_json":
                data = _safe_json_object(self._form_str(form, "tools_json"), "tools")
                cfg.tools = ToolsConfig.model_validate(data)
                self._save_config(cfg)
                self._redirect("/mcp", msg="Tools config saved")
                return

            raise ValueError("Unsupported MCP action")

        def _handle_post_skills(self, form: dict[str, list[str]]) -> None:
            cfg = self._load_config()
            action = self._form_str(form, "action")

            if action == "install_skill_library":
                entry_id = self._form_str(form, "library_skill_id").strip()
                item = find_skill_library_entry(entry_id)
                if not item:
                    raise ValueError(f"Unknown skill library entry: {entry_id}")
                ok, reason = install_skill_from_library(str(item["name"]), overwrite=self._form_bool(form, "overwrite_existing"))
                if not ok:
                    raise ValueError(reason)
                cfg.skills.disabled = [s for s in (cfg.skills.disabled or []) if s != str(item["name"])]
                self._save_config(cfg)
                self._redirect("/skills", msg=reason)
                return

            if action == "enable_skill_from_library":
                name = self._form_str(form, "skill_name").strip()
                if not name:
                    raise ValueError("skill_name is required")
                disabled = [s for s in (cfg.skills.disabled or []) if s != name]
                cfg.skills.disabled = disabled
                self._save_config(cfg)
                self._redirect("/skills", msg=f"Skill enabled: {name}")
                return

            if action == "import_skill_from_url":
                skill_name = self._form_str(form, "skill_name").strip()
                skill_url = self._form_str(form, "skill_url").strip()
                if not skill_name:
                    raise ValueError("skill_name is required")
                parsed = urlparse(skill_url)
                if parsed.scheme != "https":
                    raise ValueError("skill_url must use https://")
                if not parsed.hostname:
                    raise ValueError("skill_url must include host")
                if _is_private_or_local_host(parsed.hostname):
                    raise ValueError("skill_url host must be public")
                try:
                    req = urllib.request.Request(skill_url, headers={"User-Agent": "nanobot-webui/0.1"})
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        content_type = (resp.headers.get("Content-Type") or "").lower()
                        if content_type and "text" not in content_type and "markdown" not in content_type:
                            raise ValueError("skill_url must return text/markdown content")
                        content = resp.read(_MAX_SKILL_IMPORT_BYTES + 1)
                        if len(content) > _MAX_SKILL_IMPORT_BYTES:
                            raise ValueError("skill file is too large (max 512KB)")
                        content = content.decode("utf-8", errors="replace")
                except urllib.error.URLError as e:
                    raise ValueError(f"failed to fetch skill URL: {e}") from e
                if "# " not in content and "SKILL" not in content.upper():
                    raise ValueError("fetched content does not look like SKILL.md")
                skill_dir = get_global_skills_path() / skill_name
                skill_dir.mkdir(parents=True, exist_ok=True)
                (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
                disabled = [s for s in (cfg.skills.disabled or []) if s != skill_name]
                cfg.skills.disabled = disabled
                self._save_config(cfg)
                self._redirect("/skills", msg=f"Imported skill: {skill_name}")
                return

            if action == "save_skills_enabled":
                enabled_skills = {s.strip() for s in form.get("enabled_skill", []) if s.strip()}
                rows = _collect_skill_rows(cfg)
                all_known = [row["name"] for row in rows]
                cfg.skills.disabled = [name for name in all_known if name not in enabled_skills]
                self._save_config(cfg)
                self._redirect("/skills", msg="Skill selection saved")
                return

            if action == "save_tools_json":
                data = _safe_json_object(self._form_str(form, "tools_json"), "tools")
                cfg.tools = ToolsConfig.model_validate(data)
                self._save_config(cfg)
                self._redirect("/skills", msg="Tools config saved")
                return

            if action == "save_skills_json":
                data = _safe_json_object(self._form_str(form, "skills_json"), "skills")
                cfg.skills = SkillsConfig.model_validate(data)
                self._save_config(cfg)
                self._redirect("/skills", msg="Skills config saved")
                return

            raise ValueError("Unsupported skills action")

        def _handle_post_media(self, form: dict[str, list[str]]) -> None:
            action = self._form_str(form, "action")
            if action in {"save_exports_dir", "save_exports_dir_default"}:
                cfg = self._load_config()
                raw = self._form_str(form, "exports_dir", "").strip()
                cfg.tools.files_hub.exports_dir = "" if action == "save_exports_dir_default" else raw
                self._save_config(cfg)
                self._redirect("/media", msg="导出目录设置已保存")
                return

            scope = (self._form_str(form, "scope", "media") or "media").strip().lower()
            if scope == "exports":
                cfg = self._load_config()
                root_dir = get_exports_dir(cfg.tools.files_hub.exports_dir).resolve()
                scope_label = "导出目录"
            else:
                scope = "media"
                root_dir = get_media_dir().resolve()
                scope_label = "媒体目录"
            if action == "refresh":
                self._redirect("/media", msg=f"已刷新{scope_label}列表")
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
                p = (root_dir / name).resolve()
                try:
                    p.relative_to(root_dir)
                except ValueError:
                    continue
                if not p.exists():
                    missing += 1
                    continue
                if not p.is_file():
                    continue
                p.unlink(missing_ok=True)
                deleted += 1
            self._redirect(
                "/media",
                msg=f"{scope_label}已删除 {deleted} 个文件" + (f"，缺失 {missing} 个" if missing else ""),
            )

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
