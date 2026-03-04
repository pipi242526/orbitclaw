"""Channels page renderer for Web UI."""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any, Callable

from lunaeclaw.app.webui.common import (
    _pretty_json,
)
from lunaeclaw.app.webui.i18n import ui_copy as _ui_copy
from lunaeclaw.app.webui.i18n import ui_term as _ui_term
from lunaeclaw.app.webui.icons import icon_svg
from lunaeclaw.app.webui.view_models import (
    build_channel_overview_rows,
    build_channel_quick_models,
)
from lunaeclaw.platform.config.loader import load_config

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
    icon_save = icon_svg("save")
    gateway_runtime_ready, gateway_reason_en, gateway_reason_zh = gateway_runtime_status()
    gateway_runtime_reason = gateway_reason_zh if zh else gateway_reason_en
    channels_json = _pretty_json(cfg.channels.model_dump(by_alias=True))
    quick_model = build_channel_quick_models(cfg, cfg_resolved)
    default_quick_channel = str(quick_model["default_quick_channel"])
    quick_options: list[str] = []
    quick_cards = []
    for channel in quick_model["channels"]:
        sid = str(channel["id"])
        quick_options.append(
            f'<option value="{escape(sid)}">{escape(t_dyn(str(channel["title_en"]), str(channel["title_zh"])))}</option>'
        )

        field_rows = []
        for field in channel["fields"]:
            label_text = t_dyn(str(field["label_en"]), str(field["label_zh"]))
            field_rows.append(
                f"""
<div class="field">
  <label>{escape(label_text)}</label>
  <input type="text" name="{escape(str(field["input_name"]))}" value="{escape(str(field["display_value"]))}" placeholder="{escape(str(field["env_hint"]))}">
</div>
"""
            )

        quick_cards.append(
            f"""
<section class="card quick-channel-card is-hidden" data-channel="{escape(sid)}">
  <h3>{escape(t_dyn(str(channel["title_en"]), str(channel["title_zh"])))}</h3>
  <div class="field"><label><input type="checkbox" name="ch_{escape(sid)}_enabled" {"checked" if bool(channel["enabled"]) else ""}> {term("enabled")}</label></div>
  <div class="endpoint-fields">
    {''.join(field_rows)}
      <div class="field">
        <label>{t("credential storage", "凭据存储方式")}</label>
        <select name="ch_{escape(sid)}_auth_mode">
          <option value="env_placeholders" {"selected" if str(channel["auth_mode"]) == "env_placeholders" else ""}>{t("env placeholders (recommended)", "环境变量占位（推荐）")}</option>
          <option value="plain" {"selected" if str(channel["auth_mode"]) == "plain" else ""}>{t("plain text (not recommended)", "明文（不推荐）")}</option>
        </select>
      </div>
    <div class="field">
      <label>{t("credential env prefix", "凭据环境变量前缀")}</label>
      <input type="text" name="ch_{escape(sid)}_env_prefix" value="{escape(str(channel["env_prefix"]))}" placeholder="{escape(str(channel["default_env_prefix"]))}">
    </div>
    <div class="field full">
      <label>{t("allowFrom list (CSV)", "allowFrom 列表（逗号分隔）")}</label>
      <input type="text" name="ch_{escape(sid)}_allow_csv" value="{escape(str(channel["allow_csv"]))}" placeholder="{t('id1, id2', '用户ID1, 用户ID2')}">
    </div>
      <div class="field">
        <label>{t("allowFrom storage", "allowFrom 存储方式")}</label>
        <select name="ch_{escape(sid)}_allow_mode">
          <option value="env_placeholders" {"selected" if str(channel["allow_mode"]) == "env_placeholders" else ""}>{t("env placeholders (recommended)", "环境变量占位（推荐）")}</option>
          <option value="plain" {"selected" if str(channel["allow_mode"]) == "plain" else ""}>{t("plain list (not recommended)", "明文列表（不推荐）")}</option>
        </select>
      </div>
    <div class="field">
      <label>{t("allowFrom env prefix", "allowFrom 环境变量前缀")}</label>
      <input type="text" name="ch_{escape(sid)}_allow_env_prefix" value="{escape(str(channel["allow_prefix"]))}" placeholder="{escape(str(channel["default_allow_env_prefix"]))}">
    </div>
  </div>
</section>
"""
        )
    cards = []
    for row in build_channel_overview_rows(cfg):
        name = str(row["name"])
        enabled = bool(row["enabled"])
        snippet = str(row["snippet"] or "")
        cards.append(
            f"""
<tr>
  <td><code>{name}</code></td>
  <td>{f'<span class="pill ok">{term("enabled")}</span>' if enabled else f'<span class="pill off">{term("disabled")}</span>'}</td>
  <td class="small">{escape(snippet or term('none'))}</td>
</tr>
"""
        )
    body = f"""
<section class="card">
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
    <div class="row mt-12">
      <button class="btn primary icon-btn" type="submit">{icon_save}{t("Save Selected Channel", "保存当前渠道配置")}</button>
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
          card.classList.toggle('is-hidden', !hit);
        }}
      }}
      picker.value = hidden.value || picker.options[0].value;
      picker.addEventListener('change', showSelected);
      showSelected();
    }})();
  </script>
</section>
<div class="split mt-14">
  <section class="card">
    <h2>{t("Channel Overview", "多渠道概览")}</h2>
    <table>
      <tr><th>{t("Channel", "渠道")}</th><th>{t("Status", "状态")}</th><th>{t("Config snippet (masked)", "配置片段（脱敏）")}</th></tr>
      {''.join(cards)}
    </table>
  </section>
  <section class="card">
    <h2>{t("Global Channel Behavior", "通道行为（全局）")}</h2>
    <ul class="list small">
      <li>sendProgress: {term("on") if cfg.channels.send_progress else term("off")}</li>
      <li>sendToolHints: {term("on") if cfg.channels.send_tool_hints else term("off")}</li>
    </ul>
    <div class="muted">
      {t("Gateway auto-reload", "Gateway 自动热重载")}:
      {'OK' if gateway_runtime_ready else term("not_ready")}
      ({escape(gateway_runtime_reason)})
    </div>
  </section>
</div>
<form method="post" class="card mt-14">
  <h2>{t("Channels JSON Editor", "Channels JSON 编辑器")}</h2>
  <div class="field"><label>{t("Full channels config (supports ${ENV_VAR})", "完整 channels 配置（支持 ${ENV_VAR} 占位）")}</label>
    <textarea class="tall-lg" name="channels_json">{escape(channels_json)}</textarea>
  </div>
  <div class="row">
    <button class="btn primary icon-btn" type="submit" name="action" value="save_channels_json">{icon_save}{t("Save Channels JSON", "保存 Channels JSON")}</button>
  </div>
</form>
"""
    handler._send_html(200, handler._page(t("Channels", "渠道"), body, tab="/channels", msg=msg, err=err))
