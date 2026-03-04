"""POST handlers for WebUI channels actions."""

from __future__ import annotations

from typing import Any

from orbitclaw.app.webui.common import (
    _parse_csv,
    _safe_json_object,
    _sanitize_env_key,
)
from orbitclaw.app.webui.i18n import ui_copy as _ui_copy
from orbitclaw.app.webui.services_channels import (
    apply_quick_channel_update,
    find_quick_channel_spec,
)
from orbitclaw.platform.config.schema import ChannelsConfig


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
        env_prefix = _sanitize_env_key(
            handler._form_str(form, f"ch_{sid}_env_prefix", str(spec["env_prefix"])),
            str(spec["env_prefix"]),
        )
        submitted_fields = {
            str(field["path"]): handler._form_str(form, f"ch_{sid}_{str(field['path']).replace('.', '__')}", "").strip()
            for field in spec["fields"]
        }
        allow_values = _parse_csv(handler._form_str(form, f"ch_{sid}_allow_csv", ""))
        allow_mode = handler._form_str(form, f"ch_{sid}_allow_mode", "env_placeholders").strip()
        allow_prefix = _sanitize_env_key(
            handler._form_str(form, f"ch_{sid}_allow_env_prefix", str(spec["allow_env_prefix"])),
            str(spec["allow_env_prefix"]),
        )
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
        )

        handler._save_config(cfg)
        handler._redirect(
            "/channels",
            msg=handler._append_apply_status(
                f"Channel `{selected_channel}` saved (gateway auto-reloads if token/secret changed).",
                f"渠道 `{selected_channel}` 配置已保存（如改 token/secret，Gateway 将自动热重载）。",
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
