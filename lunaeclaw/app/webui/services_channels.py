"""Service helpers for WebUI channel mutations."""

from __future__ import annotations

import re
from typing import Any

from lunaeclaw.app.webui.common import (
    _CHANNEL_QUICK_SPECS,
    _is_env_placeholder,
    _set_nested_attr,
)
from lunaeclaw.platform.utils.helpers import get_env_file


def find_quick_channel_spec(channel_id: str) -> dict[str, Any] | None:
    selected = str(channel_id or "").strip().lower()
    for spec in _CHANNEL_QUICK_SPECS:
        if str(spec.get("id", "")).strip().lower() == selected:
            return spec
    return None


def apply_quick_channel_update(
    cfg: Any,
    *,
    spec: dict[str, Any],
    enabled: bool,
    auth_mode: str,
    env_prefix: str,
    submitted_fields: dict[str, str],
    allow_values: list[str],
    allow_mode: str,
    allow_prefix: str,
    env_updates: dict[str, str] | None = None,
) -> None:
    sid = str(spec["id"])
    channel_obj = getattr(cfg.channels, sid)
    setattr(channel_obj, "enabled", enabled)

    for field in spec["fields"]:
        path = str(field["path"])
        submitted = str(submitted_fields.get(path, "")).strip()
        if auth_mode == "env_placeholders" and field.get("env_suffix"):
            env_key = f"{env_prefix}_{field['env_suffix']}"
            next_value = f"${{{env_key}}}"
            if env_updates is not None and submitted and not _is_env_placeholder(submitted):
                env_updates[env_key] = submitted
        else:
            next_value = submitted
        _set_nested_attr(channel_obj, path, next_value)

    if allow_mode == "env_placeholders":
        allow_from = []
        for idx, raw in enumerate(allow_values):
            env_key = f"{allow_prefix}_{idx + 1}"
            allow_from.append(f"${{{env_key}}}")
            value = str(raw or "").strip()
            if env_updates is not None and value and not _is_env_placeholder(value):
                env_updates[env_key] = value
    else:
        allow_from = [v for v in allow_values if str(v).strip()]
    _set_nested_attr(channel_obj, str(spec["allow_field"]), allow_from)
    setattr(cfg.channels, sid, channel_obj)


_ENV_LINE_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")


def upsert_env_file_values(values: dict[str, str]) -> int:
    """Write or update key/value pairs in primary .env file."""
    updates = {
        str(k).strip(): str(v)
        for k, v in (values or {}).items()
        if str(k).strip() and str(v).strip()
    }
    if not updates:
        return 0

    env_path = get_env_file()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    touched: set[str] = set()
    next_lines: list[str] = []

    for line in lines:
        m = _ENV_LINE_RE.match(line)
        if not m:
            next_lines.append(line)
            continue
        key = m.group(1)
        if key in updates:
            next_lines.append(f"{key}={updates[key]}")
            touched.add(key)
        else:
            next_lines.append(line)

    for key, value in updates.items():
        if key not in touched:
            next_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")
    return len(updates)
