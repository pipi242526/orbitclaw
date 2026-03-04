"""Service helpers for WebUI channel mutations."""

from __future__ import annotations

from typing import Any

from orbitclaw.app.webui.common import (
    _CHANNEL_QUICK_SPECS,
    _set_nested_attr,
)


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
) -> None:
    sid = str(spec["id"])
    channel_obj = getattr(cfg.channels, sid)
    setattr(channel_obj, "enabled", enabled)

    for field in spec["fields"]:
        path = str(field["path"])
        submitted = str(submitted_fields.get(path, "")).strip()
        if auth_mode == "env_placeholders" and field.get("env_suffix"):
            next_value = f"${{{env_prefix}_{field['env_suffix']}}}"
        else:
            next_value = submitted
        _set_nested_attr(channel_obj, path, next_value)

    if allow_mode == "env_placeholders":
        allow_from = [f"${{{allow_prefix}_{idx + 1}}}" for idx, _ in enumerate(allow_values)]
    else:
        allow_from = [v for v in allow_values if str(v).strip()]
    _set_nested_attr(channel_obj, str(spec["allow_field"]), allow_from)
    setattr(cfg.channels, sid, channel_obj)
