"""POST handlers for WebUI channels actions."""

from __future__ import annotations

import re
from typing import Any

from lunaeclaw.app.webui.common import (
    _parse_csv,
    _safe_json_object,
    _sanitize_env_key,
)
from lunaeclaw.app.webui.i18n import ui_copy as _ui_copy
from lunaeclaw.app.webui.services_channels import (
    apply_quick_channel_update,
    find_quick_channel_spec,
    upsert_env_file_values,
)
from lunaeclaw.platform.config.schema import ChannelsConfig

_TELEGRAM_TOKEN_RE = re.compile(r"^[0-9]{6,}:[A-Za-z0-9_-]{20,}$")


def _validate_telegram_plain_token(token: str) -> str | None:
    text = str(token or "").strip()
    if not text:
        return "Telegram token is empty."
    if any(ord(ch) > 127 for ch in text):
        return "Telegram token contains non-ASCII characters; check copied punctuation."
    if not _TELEGRAM_TOKEN_RE.match(text):
        return "Telegram token format looks invalid; expected `<digits>:<token>`."
    return None


def _derive_auth_env_prefix(raw: str, *, default_prefix: str, field_suffixes: list[str]) -> str:
    cleaned = _sanitize_env_key(raw, default_prefix)
    for suffix in field_suffixes:
        token = f"_{suffix}"
        if cleaned.endswith(token) and len(cleaned) > len(token):
            return cleaned[: -len(token)]
    return cleaned


def _derive_allow_env_prefix(raw: str, *, default_prefix: str) -> str:
    cleaned = _sanitize_env_key(raw, default_prefix)
    m = re.match(r"^(.*)_\d+$", cleaned)
    if m and m.group(1):
        return m.group(1)
    return cleaned


def handle_post_channels(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /channels POST actions."""
    cfg = handler._load_config()
    action = handler._form_str(form, "action")

    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    if action == "save_channels_quick":
        selected_channel = handler._form_str(form, "quick_channel_id", "").strip().lower()
        spec = find_quick_channel_spec(selected_channel)
        if not spec:
            raise ValueError(t("Please select a valid channel.", "请选择一个有效渠道。"))
        sid = str(spec["id"])
        auth_mode = handler._form_str(form, f"ch_{sid}_auth_mode", "env_placeholders").strip()
        env_prefix = _derive_auth_env_prefix(
            handler._form_str(form, f"ch_{sid}_env_prefix", str(spec["env_prefix"])),
            default_prefix=str(spec["env_prefix"]),
            field_suffixes=[str(field.get("env_suffix") or "") for field in spec["fields"] if field.get("env_suffix")],
        )
        submitted_fields = {
            str(field["path"]): handler._form_str(form, f"ch_{sid}_{str(field['path']).replace('.', '__')}", "").strip()
            for field in spec["fields"]
        }
        allow_values = _parse_csv(handler._form_str(form, f"ch_{sid}_allow_csv", ""))
        allow_mode = handler._form_str(form, f"ch_{sid}_allow_mode", "env_placeholders").strip()
        allow_prefix = _derive_allow_env_prefix(
            handler._form_str(form, f"ch_{sid}_allow_env_prefix", str(spec["allow_env_prefix"])),
            default_prefix=str(spec["allow_env_prefix"]),
        )
        env_updates: dict[str, str] = {}
        apply_quick_channel_update(
            cfg,
            spec=spec,
            enabled=handler._form_bool(form, f"ch_{sid}_enabled"),
            auth_mode=auth_mode,
            env_prefix=env_prefix,
            submitted_fields=submitted_fields,
            allow_values=allow_values,
            allow_mode=allow_mode,
            allow_prefix=allow_prefix,
            env_updates=env_updates,
        )
        env_written = upsert_env_file_values(env_updates)

        handler._save_config(cfg)
        base_en = f"Channel `{selected_channel}` saved (gateway auto-reloads if token/secret changed)."
        base_zh = f"渠道 `{selected_channel}` 配置已保存（如改 token/secret，Gateway 将自动热重载）。"
        warn_en = ""
        warn_zh = ""
        if sid == "telegram" and handler._form_bool(form, f"ch_{sid}_enabled"):
            token_raw = submitted_fields.get("token", "")
            if auth_mode == "plain":
                token_warn = _validate_telegram_plain_token(token_raw)
                if token_warn:
                    warn_en = f" Warning: {token_warn}"
                    warn_zh = " 警告：Telegram token 格式看起来异常，请检查是否粘贴了错误字符（如中文破折号）。"
        if env_written > 0:
            base_en = f"{base_en} Synced {env_written} env var(s) to .env."
            base_zh = f"{base_zh} 已同步 {env_written} 个环境变量到 .env。"
        if warn_en:
            base_en += warn_en
        if warn_zh:
            base_zh += warn_zh
        handler._redirect(
            "/channels",
            msg=handler._append_apply_status(
                base_en,
                base_zh,
            ),
        )
        return

    if action == "save_channels_json":
        raw = handler._form_str(form, "channels_json")
        data = _safe_json_object(raw, "channels")
        cfg.channels = ChannelsConfig.model_validate(data)
        handler._save_config(cfg)
        handler._redirect(
            "/channels",
            msg=handler._append_apply_status(
                "Channels JSON saved (gateway auto-reloads if token/secret changed).",
                "Channels 配置已保存（如改了 token/secret，Gateway 将自动热重载）。",
            ),
        )
        return

    raise ValueError(t("Unsupported channels action", "不支持的渠道操作"))
