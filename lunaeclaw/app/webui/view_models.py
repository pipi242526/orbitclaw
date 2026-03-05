"""View-model builders for WebUI pages."""

from __future__ import annotations

from typing import Any

from lunaeclaw.app.webui.catalog import SKILL_LIBRARY as _SKILL_LIBRARY
from lunaeclaw.app.webui.catalog import evaluate_skill_library_health
from lunaeclaw.app.webui.common import (
    _CHANNEL_QUICK_SPECS,
    _ENV_PLACEHOLDER_RE,
    _collect_skill_rows,
    _derive_env_prefix_from_placeholders,
    _get_nested_attr,
    _is_env_placeholder,
    _mask_secret,
    _mask_sensitive_url,
)
from lunaeclaw.app.webui.services_mcp import is_mcp_server_enabled
from lunaeclaw.platform.utils.helpers import get_global_skills_path


def build_endpoint_switch_rows(cfg: Any, *, per_endpoint_limit: int = 8) -> list[dict[str, str | bool]]:
    rows: list[dict[str, str | bool]] = []
    for endpoint_name in sorted(cfg.providers.endpoints.keys()):
        endpoint = cfg.providers.endpoints[endpoint_name]
        models = endpoint.models or []
        if models:
            for model_name in models[: max(1, int(per_endpoint_limit))]:
                cmd = f"/model {endpoint_name}/{model_name}"
                rows.append(
                    {
                        "endpoint": endpoint_name,
                        "model": model_name,
                        "command": cmd,
                        "unrestricted": False,
                    }
                )
        else:
            hint = f"{endpoint_name}/<model-name>"
            rows.append(
                {
                    "endpoint": endpoint_name,
                    "model": "",
                    "command": f"/model {hint}",
                    "unrestricted": True,
                }
            )
    return rows


def build_default_model_candidates(cfg: Any) -> list[str]:
    candidates: list[str] = []
    for endpoint_name in sorted(cfg.providers.endpoints.keys()):
        endpoint = cfg.providers.endpoints[endpoint_name]
        if not endpoint.enabled:
            continue
        for model_name in endpoint.models or []:
            ref = f"{endpoint_name}/{model_name}"
            if ref not in candidates:
                candidates.append(ref)
    current = str(cfg.agents.defaults.model)
    if current and current not in candidates:
        candidates.insert(0, current)
    return candidates


def build_mcp_server_rows(cfg: Any) -> list[dict[str, str | bool]]:
    rows: list[dict[str, str | bool]] = []
    for name in sorted(cfg.tools.mcp_servers.keys()):
        server = cfg.tools.mcp_servers[name]
        target = _mask_sensitive_url(server.url) if server.url else f"{server.command} {' '.join(server.args or [])}".strip()
        rows.append(
            {
                "name": name,
                "target": target,
                "enabled": is_mcp_server_enabled(cfg, name),
            }
        )
    return rows


def build_channel_overview_rows(cfg: Any) -> list[dict[str, str | bool]]:
    rows: list[dict[str, str | bool]] = []
    channels_dump = cfg.channels.model_dump()
    for name in ["telegram", "discord", "feishu", "dingtalk", "qq", "slack", "whatsapp", "email", "mochat"]:
        item = channels_dump.get(name) or {}
        enabled = bool(item.get("enabled"))
        keys: list[str] = []
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
        rows.append({"name": name, "enabled": enabled, "snippet": "; ".join(keys)})
    return rows


def build_skill_rows(cfg: Any) -> list[dict[str, Any]]:
    return _collect_skill_rows(cfg)


def build_skill_library_rows(cfg: Any, skill_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    known_skills = {str(s["name"]) for s in skill_rows}
    disabled_values = getattr(getattr(cfg, "skills", None), "disabled", []) or []
    disabled_skills = {str(s).strip() for s in disabled_values if str(s).strip()}
    rows: list[dict[str, Any]] = []
    for item in _SKILL_LIBRARY:
        name = str(item["name"])
        exists = name in known_skills
        global_skill_file = get_global_skills_path() / name / "SKILL.md"
        global_installed = global_skill_file.exists()
        health = evaluate_skill_library_health(cfg, item, skill_rows)
        if global_installed and (name in disabled_skills) and str(health.get("status") or "") != "disabled":
            health = {"status": "disabled", "label": "disabled", "hint": "enable in selection"}
        rows.append(
            {
                "item": item,
                "name": name,
                "exists": exists,
                "skill_enabled": (name not in disabled_skills) and exists,
                "global_installed": global_installed,
                "health": health,
            }
        )
    return rows


def build_channel_quick_models(cfg: Any, cfg_resolved: Any) -> dict[str, Any]:
    channels: list[dict[str, Any]] = []
    default_quick_channel = ""
    for spec in _CHANNEL_QUICK_SPECS:
        sid = str(spec["id"])
        raw_channel = getattr(cfg.channels, sid)
        if not default_quick_channel and bool(getattr(raw_channel, "enabled", False)):
            default_quick_channel = sid
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
        first_env_suffix = str(env_fields[0]["env_suffix"]) if env_fields else ""
        env_key_name = f"{env_prefix}_{first_env_suffix}" if first_env_suffix else env_prefix
        default_env_key_name = (
            f"{str(spec['env_prefix'])}_{first_env_suffix}" if first_env_suffix else str(spec["env_prefix"])
        )

        allow_field = str(spec["allow_field"])
        allow_raw = list(_get_nested_attr(raw_channel, allow_field) or [])
        allow_resolved = list(_get_nested_attr(resolved_channel, allow_field) or [])
        allow_sample_values = [str(x).strip() for x in allow_raw if str(x).strip()]
        allow_mode = (
            "env_placeholders"
            if (allow_sample_values and all(_is_env_placeholder(x) for x in allow_sample_values))
            else "plain"
        )
        allow_prefix = _derive_env_prefix_from_placeholders(allow_sample_values, str(spec["allow_env_prefix"]))
        allow_placeholder = ", ".join(allow_sample_values) if allow_mode == "env_placeholders" else ""
        if allow_mode == "env_placeholders":
            resolved_values = [
                str(x).strip() for x in allow_resolved if str(x).strip() and not _is_env_placeholder(str(x).strip())
            ]
            # Keep unresolved placeholder examples out of input value.
            allow_csv = ", ".join(resolved_values) if resolved_values else ""
        else:
            allow_csv = ", ".join([x for x in allow_sample_values if not _is_env_placeholder(x)])
        allow_clear_on_focus = bool(allow_placeholder) and (not allow_csv or allow_csv == allow_placeholder)
        allow_key_name = f"{allow_prefix}_1"
        default_allow_key_name = f"{str(spec['allow_env_prefix'])}_1"

        fields: list[dict[str, str | bool]] = []
        for field in spec["fields"]:
            path = str(field["path"])
            input_name = f"ch_{sid}_{path.replace('.', '__')}"
            raw_value = str(_get_nested_attr(raw_channel, path) or "")
            display_value = raw_value
            clear_on_focus = False
            sample_value = ""
            if not bool(field.get("secret")) and _is_env_placeholder(raw_value):
                resolved_value = str(_get_nested_attr(resolved_channel, path) or "")
                if resolved_value:
                    display_value = resolved_value
                else:
                    clear_on_focus = True
                    sample_value = raw_value
            elif _is_env_placeholder(raw_value):
                clear_on_focus = True
                sample_value = raw_value
            env_hint = f"${{{env_prefix}_{field['env_suffix']}}}" if field.get("env_suffix") else ""
            fields.append(
                {
                    "path": path,
                    "input_name": input_name,
                    "display_value": display_value,
                    "env_hint": env_hint,
                    "clear_on_focus": clear_on_focus,
                    "sample_value": sample_value,
                    "label_en": str(field["label_en"]),
                    "label_zh": str(field["label_zh"]),
                }
            )

        channels.append(
            {
                "id": sid,
                "title_en": str(spec["title_en"]),
                "title_zh": str(spec["title_zh"]),
                "enabled": bool(getattr(raw_channel, "enabled", False)),
                "auth_mode": auth_mode,
                "env_prefix": env_prefix,
                "env_key_name": env_key_name,
                "default_env_key_name": default_env_key_name,
                "allow_mode": allow_mode,
                "allow_prefix": allow_prefix,
                "allow_key_name": allow_key_name,
                "default_allow_key_name": default_allow_key_name,
                "allow_csv": allow_csv,
                "allow_placeholder": allow_placeholder,
                "allow_clear_on_focus": allow_clear_on_focus,
                "default_env_prefix": str(spec["env_prefix"]),
                "default_allow_env_prefix": str(spec["allow_env_prefix"]),
                "fields": fields,
            }
        )
    if not default_quick_channel and channels:
        default_quick_channel = str(channels[0]["id"])
    return {"default_quick_channel": default_quick_channel, "channels": channels}
