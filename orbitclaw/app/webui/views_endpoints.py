"""Endpoints/models page renderer for Web UI."""

from __future__ import annotations

from html import escape
from typing import Any

from orbitclaw.app.webui.common import (
    _ENDPOINT_TYPES,
    _REPLY_LANGUAGE_CODES,
    _pretty_json,
)
from orbitclaw.app.webui.i18n import reply_language_label as _reply_language_label
from orbitclaw.app.webui.i18n import ui_copy as _ui_copy
from orbitclaw.app.webui.icons import icon_svg
from orbitclaw.app.webui.view_models import (
    build_default_model_candidates,
    build_endpoint_switch_rows,
)


def render_endpoints(handler: Any, *, msg: str = "", err: str = "") -> None:
    """Render the models/endpoints page."""
    cfg = handler._load_config()

    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)
    icon_copy = icon_svg("copy")
    icon_save = icon_svg("save")
    icon_delete = icon_svg("delete")
    icon_add = icon_svg("add")
    cards = []
    switch_rows_html: list[str] = []
    switch_rows = build_endpoint_switch_rows(cfg)
    for row in switch_rows:
        endpoint_name = str(row["endpoint"])
        model_name = str(row["model"])
        cmd = str(row["command"])
        unrestricted = bool(row["unrestricted"])
        if unrestricted:
            switch_rows_html.append(
                f'<tr><td><code>{escape(endpoint_name)}</code></td><td class="muted">{t("(unrestricted)", "（未限制）")}</td>'
                f'<td><code>{escape(cmd)}</code></td>'
                f'<td><button type="button" class="btn subtle icon-btn" data-copy="{escape(cmd)}" onclick="nbCopy(this.dataset.copy)">{icon_copy}{t("Copy", "复制")}</button></td></tr>'
            )
            continue
        switch_rows_html.append(
            f'<tr><td><code>{escape(endpoint_name)}</code></td><td><code>{escape(model_name)}</code></td>'
            f'<td><code>{escape(cmd)}</code></td>'
            f'<td><button type="button" class="btn subtle icon-btn" data-copy="{escape(cmd)}" onclick="nbCopy(this.dataset.copy)">{icon_copy}{t("Copy", "复制")}</button></td></tr>'
        )
    for name in sorted(cfg.providers.endpoints.keys()):
        ep = cfg.providers.endpoints[name]
        models_csv = ", ".join(ep.models or [])
        headers_json = _pretty_json(ep.extra_headers or {})
        options = "".join(
            f'<option value="{item}" {"selected" if ep.type == item else ""}>{item}</option>' for item in _ENDPOINT_TYPES
        )
        cards.append(
            f"""
<form method="post" class="endpoint-card">
  <input type="hidden" name="original_name" value="{escape(name)}">
  <div class="endpoint-head">
    <h3><code>{escape(name)}</code></h3>
    <div class="row">
      <button class="btn primary icon-btn" type="submit" name="action" value="save_endpoint">{icon_save}{t("Save", "保存")}</button>
      <button class="btn danger icon-btn" type="submit" formaction="/endpoints" name="action" value="delete_endpoint" onclick="return confirm('{t('Delete endpoint', '删除端点')} {escape(name)} ?');">{icon_delete}{t("Delete", "删除")}</button>
    </div>
  </div>
  <div class="endpoint-fields">
    <div class="field"><label>{t("Name (used by /model endpoint/model)", "名字（用于 /model endpoint/model）")}</label><input type="text" name="name" value="{escape(name)}"></div>
    <div class="field"><label>{t("Type (protocol/router)", "类型（协议/路由）")}</label><select name="type">{options}</select></div>
    <div class="field"><label>{t("API Base (supports ${ENV})", "API Base（可用 ${ENV} 占位）")}</label><input type="text" name="api_base" value="{escape(ep.api_base or '')}"></div>
    <div class="field"><label>{t("API Key (env placeholder recommended)", "API Key（建议使用 env 占位）")}</label><input type="text" name="api_key" value="{escape(ep.api_key or '')}"></div>
    <div class="field full"><label>{t("Models (CSV; empty = unrestricted)", "Models（逗号分隔；空=不限）")}</label><input type="text" name="models_csv" value="{escape(models_csv)}"></div>
    <div class="field full"><label>{t("Extra Headers JSON", "附加请求头 JSON")}</label><textarea name="extra_headers_json">{escape(headers_json)}</textarea></div>
    <div class="field"><label><input type="checkbox" name="enabled" {"checked" if ep.enabled else ""}> {t("Enable this endpoint", "启用该端点")}</label></div>
  </div>
</form>
"""
        )
    options = "".join(f'<option value="{item}">{item}</option>' for item in _ENDPOINT_TYPES)
    add_form = f"""
<form method="post" class="card">
  <h2>{t("Add Endpoint", "新增端点")}</h2>
  <input type="hidden" name="action" value="save_endpoint">
  <div class="endpoint-fields">
    <div class="field"><label>{t("Name", "名字")}</label><input type="text" name="name" placeholder="myopen"></div>
    <div class="field"><label>{t("Type", "类型")}</label><select name="type">{options}</select></div>
    <div class="field"><label>{t("API Base", "API 地址")}</label><input type="text" name="api_base" placeholder="${'{'}MYOPEN_BASE{'}'}"></div>
    <div class="field"><label>{t("API Key", "API 密钥")}</label><input type="text" name="api_key" placeholder="${'{'}MYOPEN_KEY{'}'}"></div>
    <div class="field full"><label>{t("Models (CSV)", "Models（逗号分隔）")}</label><input type="text" name="models_csv" placeholder="qwen-max, deepseek-v3"></div>
    <div class="field full"><label>{t("Extra Headers JSON", "附加请求头 JSON")}</label><textarea name="extra_headers_json">{{}}</textarea></div>
    <div class="field"><label><input type="checkbox" name="enabled" checked> {t("Enabled", "启用")}</label></div>
  </div>
  <div class="row">
    <button class="btn primary icon-btn" type="submit">{icon_add}{t("Create Endpoint", "新增端点")}</button>
  </div>
</form>
"""
    reply_lang_options_html = "".join(
        f'<option value="{escape(v)}" {"selected" if cfg.agents.defaults.reply_language == v else ""}>{escape(_reply_language_label(handler._ui_lang, v))}</option>'
        for v in _REPLY_LANGUAGE_CODES
    )
    fallback_lang_options_html = "".join(
        f'<option value="{escape(v)}" {"selected" if cfg.agents.defaults.auto_reply_fallback_language == v else ""}>{escape(_reply_language_label(handler._ui_lang, v))}</option>'
        for v in _REPLY_LANGUAGE_CODES
    )
    default_model_candidates = build_default_model_candidates(cfg)
    default_model_options = "".join(
        f'<option value="{escape(v)}" {"selected" if v == cfg.agents.defaults.model else ""}>{escape(v)}</option>'
        for v in default_model_candidates
    )

    helper = f"""
<style>
  .endpoint-default-select {{
    min-width: min(380px, 100%);
    flex: 1 1 300px;
  }}
  .endpoint-default-input {{
    flex: 1 1 260px;
  }}
</style>
<section class="card">
  <h2>{t("Default Model", "默认模型")}</h2>
  <form method="post" class="row">
    <input type="hidden" name="action" value="set_default_model">
    <select name="default_model_select" class="endpoint-default-select">
      {default_model_options}
    </select>
    <input type="text" name="default_model_custom" class="endpoint-default-input" placeholder="{t('custom endpoint/model (optional)', '自定义 endpoint/model（可选）')}">
    <button class="btn primary icon-btn" type="submit">{icon_save}{t("Save Default Model", "保存默认模型")}</button>
  </form>
</section>
<section class="card mt-14">
  <h2>{t("Language & Search Policy", "语言与搜索策略")}</h2>
  <form method="post">
    <input type="hidden" name="action" value="set_agent_preferences">
    <div class="endpoint-fields">
      <div class="field">
        <label>{t("Default reply language (final answer)", "默认回复语言（最终回复）")}</label>
        <select name="reply_language">
          {reply_lang_options_html}
        </select>
      </div>
      <div class="field">
        <label>{t("Fallback language when auto-detect fails", "自动检测失败时的回退语言")}</label>
        <select name="auto_reply_fallback_language">
          {fallback_lang_options_html}
        </select>
      </div>
      <div class="field">
        <label><input type="checkbox" name="cross_lingual_search" {"checked" if cfg.agents.defaults.cross_lingual_search else ""}> {t("Enable cross-lingual search hints (region topics prioritize local-language retrieval)", "启用跨语言搜索提示（地区话题优先本地语言检索）")}</label>
      </div>
    </div>
    <div class="row">
      <button class="btn primary icon-btn" type="submit">{icon_save}{t("Save Language/Search Policy", "保存语言/搜索策略")}</button>
    </div>
  </form>
</section>
<section class="card mt-14">
  <h2>{t("Runtime & Context Budgets", "资源与上下文预算")}</h2>
  <form method="post">
    <input type="hidden" name="action" value="set_agent_runtime_budget">
    <div class="endpoint-fields">
      <div class="field"><label>{t("history char budget (maxHistoryChars)", "history 字符预算（maxHistoryChars）")}</label><input type="number" min="0" name="max_history_chars" value="{cfg.agents.defaults.max_history_chars}"></div>
      <div class="field"><label>{t("memory char budget (maxMemoryContextChars)", "MEMORY 字符预算（maxMemoryContextChars）")}</label><input type="number" min="0" name="max_memory_context_chars" value="{cfg.agents.defaults.max_memory_context_chars}"></div>
      <div class="field"><label>{t("background char budget (maxBackgroundContextChars)", "背景字符预算（maxBackgroundContextChars）")}</label><input type="number" min="0" name="max_background_context_chars" value="{cfg.agents.defaults.max_background_context_chars}"></div>
      <div class="field"><label>{t("inline image size cap (maxInlineImageBytes)", "内联图片大小上限（maxInlineImageBytes）")}</label><input type="number" min="0" name="max_inline_image_bytes" value="{cfg.agents.defaults.max_inline_image_bytes}"></div>
      <div class="field"><label><input type="checkbox" name="auto_compact_background" {"checked" if cfg.agents.defaults.auto_compact_background else ""}> {t("Auto-compact background (structured first, truncate later)", "自动压缩背景信息（优先结构化压缩，再截断）")}</label></div>
      <div class="field"><label>{t("system prompt cache TTL (systemPromptCacheTtlSeconds)", "系统提示缓存秒数（systemPromptCacheTtlSeconds）")}</label><input type="number" min="0" name="system_prompt_cache_ttl_seconds" value="{cfg.agents.defaults.system_prompt_cache_ttl_seconds}"></div>
      <div class="field"><label>{t("session cache cap (sessionCacheMaxEntries)", "会话缓存上限（sessionCacheMaxEntries）")}</label><input type="number" min="1" name="session_cache_max_entries" value="{cfg.agents.defaults.session_cache_max_entries}"></div>
      <div class="field"><label>{t("GC interval in turns (gcEveryTurns, 0=off)", "GC 间隔轮次（gcEveryTurns，0=关闭）")}</label><input type="number" min="0" name="gc_every_turns" value="{cfg.agents.defaults.gc_every_turns}"></div>
      <div class="field"><label>{t("per-turn timeout in seconds (turnTimeoutSeconds)", "单轮超时秒数（turnTimeoutSeconds）")}</label><input type="number" min="5" name="turn_timeout_seconds" value="{cfg.agents.defaults.turn_timeout_seconds}"></div>
      <div class="field"><label>{t("inbound queue max size (inboundQueueMaxsize, 0=unbounded)", "入站队列上限（inboundQueueMaxsize，0=无限制）")}</label><input type="number" min="0" name="inbound_queue_maxsize" value="{cfg.agents.defaults.inbound_queue_maxsize}"></div>
      <div class="field"><label>{t("outbound queue max size (outboundQueueMaxsize, 0=unbounded)", "出站队列上限（outboundQueueMaxsize，0=无限制）")}</label><input type="number" min="0" name="outbound_queue_maxsize" value="{cfg.agents.defaults.outbound_queue_maxsize}"></div>
    </div>
    <div class="row">
      <button class="btn primary icon-btn" type="submit">{icon_save}{t("Save Runtime Budget", "保存资源策略")}</button>
    </div>
  </form>
</section>
<section class="card mt-14">
    <h2>{t("In-chat quick switch commands", "聊天内快捷切换命令")}</h2>
  <table>
    <tr><th>{t("Endpoint", "端点")}</th><th>{t("Model", "模型")}</th><th>/model {t("command", "命令")}</th><th></th></tr>
    {''.join(switch_rows_html) or f'<tr><td colspan="4" class="muted">{t("Add an endpoint first; this table generates quick commands after models are configured.", "先新增 endpoint；配置 models 后这里会生成快捷命令。")}</td></tr>'}
  </table>
</section>
"""
    empty_endpoints_html = (
        f'<section class="card"><div class="muted">{t("No named endpoint yet. Add one first.", "还没有命名端点。先新增一个即可。")}</div></section>'
    )
    body = f'<div class="grid">{helper}{add_form}{"".join(cards) or empty_endpoints_html}</div>'
    handler._send_html(200, handler._page(t("Models & APIs", "模型与接口"), body, tab="/endpoints", msg=msg, err=err))
