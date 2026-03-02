"""Channels page renderer for Web UI."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Callable

from nanobot.config.loader import load_config
from nanobot.webui.common import (
    _CHANNEL_QUICK_SPECS,
    _ENV_PLACEHOLDER_RE,
    _derive_env_prefix_from_placeholders,
    _get_nested_attr,
    _is_env_placeholder,
    _mask_secret,
    _pretty_json,
)
from nanobot.webui.i18n import ui_copy as _ui_copy
from nanobot.webui.i18n import ui_term as _ui_term

GatewayRuntimeFn = Callable[[], tuple[bool, str, str]]


def render_channels(
    handler: Any,
    *,
    cfg_path: Path,
    gateway_runtime_status: GatewayRuntimeFn,
    msg: str = "",
    err: str = "",
) -> None:
    """Render the channels page."""
    cfg = handler._load_config()
    cfg_resolved = load_config(cfg_path, apply_profiles=False, resolve_env=True)
    zh = handler._ui_lang == "zh-CN"
    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    def t_dyn(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn, track=False)

    def term(key: str) -> str:
        return _ui_term(handler._ui_lang, key)
    gateway_runtime_ready, gateway_reason_en, gateway_reason_zh = gateway_runtime_status()
    gateway_runtime_reason = gateway_reason_zh if zh else gateway_reason_en
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
            f'<option value="{escape(sid)}">{escape(t_dyn(str(spec["title_en"]), str(spec["title_zh"])))}</option>'
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
            label_text = t_dyn(str(field["label_en"]), str(field["label_zh"]))
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
  <h3>{escape(t_dyn(str(spec['title_en']), str(spec['title_zh'])))}</h3>
  <div class="field"><label><input type="checkbox" name="ch_{escape(sid)}_enabled" {"checked" if bool(getattr(raw_channel, "enabled", False)) else ""}> {term("enabled")}</label></div>
  <div class="endpoint-fields">
    {''.join(field_rows)}
      <div class="field">
        <label>{t("credential storage", "凭据存储方式")}</label>
        <select name="ch_{escape(sid)}_auth_mode">
          <option value="env_placeholders" {"selected" if auth_mode == "env_placeholders" else ""}>{t("env placeholders (recommended)", "环境变量占位（推荐）")}</option>
          <option value="plain" {"selected" if auth_mode == "plain" else ""}>{t("plain text (not recommended)", "明文（不推荐）")}</option>
        </select>
      </div>
    <div class="field">
      <label>{t("credential env prefix", "凭据环境变量前缀")}</label>
      <input type="text" name="ch_{escape(sid)}_env_prefix" value="{escape(env_prefix)}" placeholder="{escape(str(spec['env_prefix']))}">
    </div>
    <div class="field full">
      <label>{t("allowFrom list (CSV)", "allowFrom 列表（逗号分隔）")}</label>
      <input type="text" name="ch_{escape(sid)}_allow_csv" value="{escape(allow_csv)}" placeholder="{t('id1, id2', '用户ID1, 用户ID2')}">
    </div>
      <div class="field">
        <label>{t("allowFrom storage", "allowFrom 存储方式")}</label>
        <select name="ch_{escape(sid)}_allow_mode">
          <option value="env_placeholders" {"selected" if allow_mode == "env_placeholders" else ""}>{t("env placeholders (recommended)", "环境变量占位（推荐）")}</option>
          <option value="plain" {"selected" if allow_mode == "plain" else ""}>{t("plain list (not recommended)", "明文列表（不推荐）")}</option>
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
  <td>{f'<span class="pill ok">{term("enabled")}</span>' if enabled else f'<span class="pill off">{term("disabled")}</span>'}</td>
  <td class="small">{escape('; '.join(keys) or term('none'))}</td>
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
      <tr><th>{t("Channel", "渠道")}</th><th>{t("Status", "状态")}</th><th>{t("Config snippet (masked)", "配置片段（脱敏）")}</th></tr>
      {''.join(cards)}
    </table>
    <div class="muted" style="margin-top:8px">{t("Use JSON editor below for full control of all channel fields.", "下方 JSON 编辑器可覆盖全部 channel 字段。")}</div>
  </section>
  <section class="card">
    <h2>{t("Global Channel Behavior", "通道行为（全局）")}</h2>
    <ul class="list small">
      <li>sendProgress: {term("on") if cfg.channels.send_progress else term("off")}</li>
      <li>sendToolHints: {term("on") if cfg.channels.send_tool_hints else term("off")} ({t("recommended off", "建议关闭")})</li>
      <li>{t("For TG-heavy usage, keep", "主用 TG 时建议保持")} <code>sendToolHints=false</code></li>
      <li>{t("allowFrom supports both plain IDs and env placeholders; team sharing usually prefers env placeholders.", "allowFrom 同时支持明文和环境变量占位；团队共享配置通常建议用 env 占位。")}</li>
    </ul>
    <div class="muted">
      {t("Gateway auto-reload", "Gateway 自动热重载")}:
      {'OK' if gateway_runtime_ready else term("not_ready")}
      ({escape(gateway_runtime_reason)})
    </div>
    <div class="muted">{t("Auto-apply is guaranteed only when WebUI and gateway share the same NANOBOT_DATA_DIR and gateway is alive.", "仅当 WebUI 与 gateway 使用同一个 NANOBOT_DATA_DIR 且 gateway 在线时，才能保证自动生效。")}</div>
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
    handler._send_html(200, handler._page(t("Channels", "渠道"), body, tab="/channels", msg=msg, err=err))
