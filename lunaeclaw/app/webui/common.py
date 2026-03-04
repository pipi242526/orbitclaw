"""Shared constants and utilities used across WebUI modules."""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from orbitclaw.platform.config.schema import Config
from orbitclaw.platform.providers.endpoint_validator import validate_default_model_reference
from orbitclaw.platform.utils.helpers import get_media_dir

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

_REPLY_LANGUAGE_CODES = [
    "auto",
    "zh-CN",
    "en",
    "ja",
    "ko",
    "fr",
    "de",
    "es",
]

_MAX_SKILL_IMPORT_BYTES = 512 * 1024
_MAX_REMOTE_JSON_BYTES = 1024 * 1024
_MEDIA_PAGE_SIZE = 50

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


def _derive_env_prefix_from_placeholders(values: list[str], default_prefix: str) -> str:
    for raw in values or []:
        m = _ENV_PLACEHOLDER_RE.match((raw or "").strip())
        if not m:
            continue
        key = m.group(1)
        if "_" in key:
            return key.rsplit("_", 1)[0]
    return default_prefix


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


def _check_default_model_ref(config: Config, model_ref: str, *, probe_remote: bool = False) -> tuple[bool, str]:
    return validate_default_model_reference(config, model_ref, probe_remote=probe_remote)


def _fetch_public_json(url: str, *, max_bytes: int = _MAX_REMOTE_JSON_BYTES) -> Any:
    parsed = urlparse((url or "").strip())
    if parsed.scheme != "https":
        raise ValueError("URL must use https://")
    if not parsed.hostname:
        raise ValueError("URL must include host")
    if _is_private_or_local_host(parsed.hostname):
        raise ValueError("URL host must be public")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "orbitclaw-webui/0.1"})
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


def _collect_skill_rows(config: Config) -> list[dict[str, Any]]:
    try:
        from orbitclaw.core.context.skills import SkillsLoader
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
