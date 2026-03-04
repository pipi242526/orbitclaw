"""WebUI page renderers extracted from the HTTP handler.

The renderers accept the request handler instance so we keep behavior unchanged
while reducing coupling/size in server.py.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path
from typing import Any, Callable

from lunaeclaw.app.webui.common import (
    _CHANNEL_QUICK_SPECS,
    _check_default_model_ref,
    _list_media_rows,
    _list_store_rows,
)
from lunaeclaw.app.webui.diagnostics import collect_config_migration_hints
from lunaeclaw.app.webui.i18n import ui_copy as _ui_copy
from lunaeclaw.app.webui.i18n import ui_term as _ui_term
from lunaeclaw.app.webui.icons import icon_svg
from lunaeclaw.app.webui.services import record_runtime_trend_sample
from lunaeclaw.app.webui.views_channels import render_channels as _render_channels_page
from lunaeclaw.app.webui.views_chat import render_chat as _render_chat_page
from lunaeclaw.app.webui.views_endpoints import render_endpoints as _render_endpoints_page
from lunaeclaw.app.webui.views_mcp import render_mcp as _render_mcp_page
from lunaeclaw.app.webui.views_media import render_media as _render_media_page
from lunaeclaw.app.webui.views_skills import render_skills as _render_skills_page
from lunaeclaw.core.context.context import ContextBuilder
from lunaeclaw.platform.config.loader import load_config
from lunaeclaw.platform.config.schema import Config
from lunaeclaw.platform.utils.budget import (
    collect_runtime_budget_alerts,
)
from lunaeclaw.platform.utils.budget import (
    estimate_tokens_from_chars as _estimate_tokens_from_chars,
)
from lunaeclaw.platform.utils.budget import (
    read_host_resource_snapshot as _read_host_resource_snapshot,
)
from lunaeclaw.platform.utils.helpers import (
    get_env_dir,
    get_env_file,
    get_exports_dir,
    get_global_skills_path,
)
from lunaeclaw.services.session.manager import SessionManager

GatewayRuntimeFn = Callable[[], tuple[bool, str, str]]
ChannelIssuesFn = Callable[[Config, Config, str], list[str]]


def render_dashboard(
    handler: Any,
    *,
    cfg_path: Path,
    gateway_state_path: Path,
    gateway_runtime_status: GatewayRuntimeFn,
    collect_channel_runtime_issues: ChannelIssuesFn,
    msg: str = "",
    err: str = "",
) -> None:
    """Render the dashboard page."""
    cfg = handler._load_config()
    cfg_resolved = load_config(cfg_path, apply_profiles=False, resolve_env=True)
    zh = handler._ui_lang == "zh-CN"
    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    def term(key: str) -> str:
        return _ui_term(handler._ui_lang, key)
    icon_chat = icon_svg("chat")
    icon_channels = icon_svg("channels")
    icon_model = icon_svg("model")
    icon_mcp = icon_svg("mcp")
    icon_media = icon_svg("media")
    channels_data = cfg.channels.model_dump()
    channel_names = [str(x["id"]) for x in _CHANNEL_QUICK_SPECS]
    enabled_channels = [name for name in channel_names if bool((channels_data.get(name) or {}).get("enabled"))]
    endpoint_names = sorted(cfg.providers.endpoints.keys())
    mcp_servers = cfg.tools.mcp_servers or {}
    media_count = len(_list_media_rows())
    export_count = len(_list_store_rows(get_exports_dir(cfg.tools.files_hub.exports_dir)))
    default_model_ok, default_model_reason = _check_default_model_ref(
        cfg_resolved,
        cfg.agents.defaults.model,
    )
    channel_issues = collect_channel_runtime_issues(cfg, cfg_resolved, handler._ui_lang)
    config_hints = collect_config_migration_hints(cfg_path)
    gateway_runtime_ready, gateway_reason_en, gateway_reason_zh = gateway_runtime_status()
    issues = [*channel_issues]
    if not gateway_runtime_ready:
        issues.append(
            f"gateway runtime: {gateway_reason_zh if zh else gateway_reason_en}"
        )
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
    snapshot = _read_host_resource_snapshot()
    record_runtime_trend_sample(snapshot)
    budget_alerts = collect_runtime_budget_alerts(cfg_resolved, snapshot)
    penalty = (len(issues) * 15) + sum(18 if a.get("severity") == "error" else 8 for a in budget_alerts)
    health_score = max(0, 100 - penalty)
    # Hard gate: if core gateway runtime is not ready, system is fundamentally unhealthy.
    if not gateway_runtime_ready:
        health_score = min(health_score, 15)
    ready_channel_count = max(0, len(enabled_channels) - len({x.split(":", 1)[0] for x in channel_issues}))
    load1 = snapshot.get("load1")
    cpu_cores = snapshot.get("cpu_cores")
    mem_used_percent = snapshot.get("mem_used_percent")
    disk_used_percent = snapshot.get("disk_used_percent")
    cpu_ratio_percent = None
    if isinstance(load1, float) and isinstance(cpu_cores, int) and cpu_cores > 0:
        cpu_ratio_percent = (load1 / cpu_cores) * 100.0

    history_chars = int(cfg.agents.defaults.max_history_chars)
    memory_chars = int(cfg.agents.defaults.max_memory_context_chars)
    background_chars = int(cfg.agents.defaults.max_background_context_chars)
    total_chars_budget = max(0, history_chars + memory_chars + background_chars)
    total_tokens_budget = _estimate_tokens_from_chars(total_chars_budget)
    inline_image_mb = max(0.0, cfg.agents.defaults.max_inline_image_bytes / 1024 / 1024)

    def _action_row(message: str, href: str, label: str) -> str:
        return (
            "<li>"
            f"<span class='issue-main'>{escape(message)}</span>"
            f"<a class='btn subtle issue-link' href='{href}' title='{escape(message)}'>{escape(label)}</a>"
            "</li>"
        )

    action_rows = []
    for item in issues[:6]:
        if item.startswith("default model:"):
            action_rows.append(_action_row(item, "/endpoints", t("fix in Models & APIs", "去模型与接口修复")))
        elif item.startswith("endpoint `"):
            action_rows.append(_action_row(item, "/endpoints", t("open endpoint and resave models", "打开端点后重新保存 models")))
        elif "exa_mcp" in item:
            action_rows.append(_action_row(item, "/mcp", t("fix in MCP page", "去 MCP 页面修复")))
        elif item.startswith("config:"):
            action_rows.append(_action_row(item, "/", t("review config migration hints and resave related page", "查看配置迁移提示后到对应页面重存")))
        elif item.startswith("gateway runtime:"):
            action_rows.append(_action_row(item, "/", t("ensure gateway uses same LUNAECLAW_DATA_DIR and is running", "确保 gateway 使用相同 LUNAECLAW_DATA_DIR 并处于运行中")))
        else:
            action_rows.append(_action_row(item, "/channels", t("fix in Channels page", "去渠道页面修复")))
    for alert in budget_alerts[:4]:
        severity = str(alert.get("severity") or "warn").upper()
        message = str(alert.get("message") or "").strip()
        suggestion = str(alert.get("suggestion") or "").strip()
        if not message:
            continue
        msg = f"[{severity}] {message}" + (f" · {suggestion}" if suggestion else "")
        action_rows.append(_action_row(msg, "/endpoints", t("tune budgets", "调整预算")))
    budget_rows = []
    for alert in budget_alerts[:5]:
        severity = str(alert.get("severity") or "warn").upper()
        message = str(alert.get("message") or "").strip()
        suggestion = str(alert.get("suggestion") or "").strip()
        if not message:
            continue
        budget_rows.append(
            f"<li><code>{escape(severity)}</code> {escape(message)}"
            f"{f' · {escape(suggestion)}' if suggestion else ''}</li>"
        )

    def meter_row(label: str, value_text: str, percent: float | None, tone: str = "teal") -> str:
        width = max(0.0, min(100.0, float(percent))) if isinstance(percent, (int, float)) else 0.0
        unknown = not isinstance(percent, (int, float))
        percent_text = f"{width:.1f}%" if not unknown else "n/a"
        tip_html = f"<div class='meter-tip muted'>{t('no metric yet', '暂无指标数据')}</div>" if unknown else ""
        return (
            "<div class='meter-row'>"
            f"<div class='meter-head'><span>{escape(label)}</span><span class='meter-head-right'><span class='mono'>{escape(value_text)}</span><span class='meter-badge'>{escape(percent_text)}</span></span></div>"
            f"<div class='meter-track'><div class='meter-fill {escape(tone)}' style='width:{width:.1f}%'></div></div>"
            f"{tip_html}"
            "</div>"
        )

    cb = ContextBuilder(
        cfg.workspace_path,
        max_history_chars=history_chars,
        max_memory_context_chars=memory_chars,
        max_background_context_chars=background_chars,
        max_inline_image_bytes=int(cfg.agents.defaults.max_inline_image_bytes or 0),
        auto_compact_background=bool(cfg.agents.defaults.auto_compact_background),
        system_prompt_cache_ttl_seconds=int(cfg.agents.defaults.system_prompt_cache_ttl_seconds or 0),
    )
    session_manager = SessionManager(
        cfg.workspace_path,
        max_cache_entries=max(1, int(cfg.agents.defaults.session_cache_max_entries)),
    )
    latest_history: list[dict[str, Any]] = []
    try:
        sessions = session_manager.list_sessions()
        if sessions:
            first_session_key = str(sessions[0].get("key") or "")
            if first_session_key:
                latest_session = session_manager.get_or_create(first_session_key)
                latest_history = latest_session.get_history(max_messages=500)
    except Exception:
        latest_history = []

    history_used_chars = 0
    if history_chars > 0 and latest_history:
        for idx, msg in enumerate(reversed(latest_history)):
            msg_size = cb._estimate_message_chars(msg)
            if idx > 0 and (history_used_chars + msg_size) > history_chars:
                break
            history_used_chars += msg_size
            if history_used_chars >= history_chars:
                break
    history_used_chars = min(history_chars, history_used_chars)
    history_left_chars = max(0, history_chars - history_used_chars)

    memory_ctx = cb.memory.get_memory_context()
    memory_used_chars = min(memory_chars, len(memory_ctx))
    memory_left_chars = max(0, memory_chars - memory_used_chars)

    bootstrap = cb._load_bootstrap_files()
    always_content = cb.skills.load_skills_for_context(cb.skills.get_always_skills())
    skills_summary = cb.skills.build_skills_summary()
    background_source_len = len(bootstrap) + len(always_content) + len(skills_summary)
    background_used_chars = min(background_chars, background_source_len)
    background_left_chars = max(0, background_chars - background_used_chars)

    history_tokens = _estimate_tokens_from_chars(history_used_chars)
    memory_tokens = _estimate_tokens_from_chars(memory_used_chars)
    background_tokens = _estimate_tokens_from_chars(background_used_chars)
    history_ratio = (history_used_chars / history_chars * 100.0) if history_chars > 0 else 0.0
    memory_ratio = (memory_used_chars / memory_chars * 100.0) if memory_chars > 0 else 0.0
    background_ratio = (background_used_chars / background_chars * 100.0) if background_chars > 0 else 0.0
    risk_count = len(issues) + len(budget_alerts)
    if not gateway_runtime_ready:
        health_state_en, health_state_zh, health_tone = "Core Offline", "主程序未启动", "risk"
    elif health_score >= 85:
        health_state_en, health_state_zh, health_tone = "Excellent", "优秀", "good"
    elif health_score >= 70:
        health_state_en, health_state_zh, health_tone = "Stable", "稳定", "good"
    elif health_score >= 50:
        health_state_en, health_state_zh, health_tone = "Needs Attention", "需关注", "warn"
    else:
        health_state_en, health_state_zh, health_tone = "At Risk", "有风险", "risk"
    model_stat_tone = "good" if default_model_ok else "risk"
    config_stat_tone = "warn" if len(config_hints) > 0 else "good"
    budget_stat_tone = "warn" if len(budget_alerts) > 0 else "good"
    files_stat_tone = "good" if (media_count + export_count) > 0 else "warn"
    body = f"""
<style>
  .overview-top {{
    display:grid;
    grid-template-columns: 1.2fr .8fr;
    gap:12px;
    margin-bottom:12px;
  }}
  .health-panel {{
    border:1px solid color-mix(in srgb, var(--line) 82%, #fff 18%);
    border-radius: 14px;
    padding: 12px;
    background:
      radial-gradient(circle at 80% 22%, color-mix(in srgb, var(--accent) 18%, transparent), transparent 48%),
      radial-gradient(circle at 14% 82%, color-mix(in srgb, var(--meter-teal-a) 12%, transparent), transparent 54%),
      linear-gradient(180deg, color-mix(in srgb, var(--card-strong) 90%, #fff 10%), color-mix(in srgb, var(--card) 88%, transparent));
    box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 34%, transparent), 0 18px 30px color-mix(in srgb, var(--line) 26%, transparent);
    display:grid;
    gap:8px;
    align-content: start;
    position: relative;
  }}
  .health-panel::after {{
    content:"";
    position:absolute;
    inset:10px 12px;
    border-radius: 12px;
    background:
      repeating-linear-gradient(90deg, color-mix(in srgb, var(--line) 18%, transparent) 0 1px, transparent 1px 24px),
      repeating-linear-gradient(0deg, color-mix(in srgb, var(--line) 14%, transparent) 0 1px, transparent 1px 24px);
    opacity:.25;
    pointer-events: none;
  }}
  .health-panel > * {{
    position: relative;
    z-index: 1;
  }}
  .health-headline {{ display:grid; grid-template-columns:auto 1fr; align-items:end; gap:12px; }}
  .health-score {{
    font-size: 44px;
    line-height: .95;
    font-weight: 760;
    letter-spacing: .3px;
    color: color-mix(in srgb, var(--ink) 88%, #1c3f6f 12%);
  }}
  .health-meta {{ display:grid; gap:4px; }}
  .health-state {{
    display:inline-flex;
    align-items:center;
    gap:6px;
    border:1px solid var(--line);
    border-radius:999px;
    padding: 3px 10px;
    width: fit-content;
    font-size: 12px;
    font-weight: 650;
    background: var(--subtle-bg);
  }}
  .health-state.good {{ border-color: color-mix(in srgb, var(--success) 46%, var(--line)); color: color-mix(in srgb, var(--success) 78%, #1f4f46 22%); }}
  .health-state.warn {{ border-color: color-mix(in srgb, var(--warning) 52%, var(--line)); color: color-mix(in srgb, var(--warning) 74%, #754522 26%); }}
  .health-state.risk {{ border-color: color-mix(in srgb, var(--err) 52%, var(--line)); color: color-mix(in srgb, var(--err) 76%, #732d2d 24%); }}
  .health-kpis {{
    display:grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap:7px;
    margin-top: 2px;
  }}
  .health-scan {{
    height: 12px;
    border-radius: 999px;
    border:1px solid color-mix(in srgb, var(--line) 58%, transparent);
    overflow: hidden;
    background:
      repeating-linear-gradient(
        90deg,
        var(--meter-track-a) 0 14px,
        var(--meter-track-b) 14px 18px
      );
  }}
  .health-scan > span {{
    display:block;
    height:100%;
    background:
      repeating-linear-gradient(
        90deg,
        color-mix(in srgb, var(--meter-teal-a) 70%, #fff 30%) 0 12px,
        color-mix(in srgb, var(--meter-teal-b) 84%, #fff 16%) 12px 16px
      );
    box-shadow: inset 0 0 0 1px color-mix(in srgb, #2d6f68 26%, transparent);
  }}
  .mini-kpi {{
    border:1px solid color-mix(in srgb, var(--line) 80%, #fff 20%);
    border-radius: 10px;
    padding: 8px 9px;
    background: color-mix(in srgb, var(--subtle-bg) 84%, transparent);
    min-height: 88px;
    display: grid;
    align-content: center;
  }}
  .mini-kpi .v {{ font-size: 20px; font-weight: 760; line-height:1.04; }}
  .mini-kpi .l {{ font-size: 11px; color: var(--muted); margin-top:3px; }}
  .health-ambient {{
    margin-top: 8px;
    display: grid;
    grid-template-columns: repeat(12, minmax(0, 1fr));
    gap: 6px;
    opacity: .8;
  }}
  .health-ambient > span {{
    height: 6px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--meter-teal-a) 42%, var(--subtle-bg));
    border: 1px solid color-mix(in srgb, var(--line) 62%, transparent);
  }}
  .health-ambient > span:nth-child(3n) {{
    background: color-mix(in srgb, var(--meter-ink-a) 40%, var(--subtle-bg));
    opacity: .75;
  }}
  .health-ambient > span:nth-child(4n) {{
    background: color-mix(in srgb, var(--meter-orange-a) 35%, var(--subtle-bg));
    opacity: .7;
  }}
  .side-stack {{ display:grid; gap:7px; }}
  .side-stat {{
    border:1px solid color-mix(in srgb, var(--line) 78%, #fff 22%);
    border-radius: 10px;
    padding:8px 10px;
    background: color-mix(in srgb, var(--subtle-bg) 82%, transparent);
  }}
  .side-stat.good {{
    border-color: color-mix(in srgb, var(--success) 36%, var(--line));
    background: color-mix(in srgb, var(--success) 11%, var(--subtle-bg));
  }}
  .side-stat.warn {{
    border-color: color-mix(in srgb, var(--warning) 38%, var(--line));
    background: color-mix(in srgb, var(--warning) 11%, var(--subtle-bg));
  }}
  .side-stat.risk {{
    border-color: color-mix(in srgb, var(--err) 42%, var(--line));
    background: color-mix(in srgb, var(--err) 10%, var(--subtle-bg));
  }}
  .side-stat .k {{ font-size: 12px; color: var(--muted); }}
  .side-stat .v {{ margin-top:3px; font-size: 22px; font-weight: 760; line-height:1; }}
  .side-stat .s {{
    margin-top:3px;
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }}
  .meter-grid {{ display:grid; gap:8px; margin-top:8px; }}
  .meter-row {{
    border:1px solid color-mix(in srgb, var(--line) 78%, #fff 22%);
    border-radius: 10px;
    padding:7px 8px;
    background: linear-gradient(180deg, color-mix(in srgb, var(--card-strong) 86%, #fff 14%), color-mix(in srgb, var(--card) 88%, transparent));
    box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 32%, transparent);
  }}
  .meter-head {{ display:flex; justify-content:space-between; gap:8px; font-size:12px; margin-bottom:6px; align-items:center; }}
  .meter-head-right {{ display:inline-flex; align-items:center; gap:8px; }}
  .meter-badge {{
    border:1px solid var(--line);
    border-radius:999px;
    padding:1px 8px;
    font-size:10px;
    color: var(--muted);
    background: var(--subtle-bg);
  }}
  html[data-theme="dark"] .health-panel {{
    border-color: color-mix(in srgb, var(--line) 92%, #fff 8%);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.12), 0 20px 40px rgba(2, 8, 20, .66);
  }}
  html[data-theme="dark"] .health-ambient > span {{
    border-color: color-mix(in srgb, var(--line) 86%, transparent);
  }}
  html[data-theme="dark"] .health-score {{
    color: color-mix(in srgb, var(--ink) 94%, #fff 6%);
    text-shadow: 0 0 14px color-mix(in srgb, var(--accent) 42%, transparent);
  }}
  html[data-theme="dark"] .meter-badge,
  html[data-theme="dark"] .summary-pill {{
    border-color: color-mix(in srgb, var(--line) 92%, #fff 8%);
  }}
  @media (prefers-color-scheme: dark) {{
    html[data-theme="auto"] .health-panel {{
      border-color: color-mix(in srgb, var(--line) 92%, #fff 8%);
      box-shadow: inset 0 1px 0 rgba(255,255,255,.12), 0 20px 40px rgba(2, 8, 20, .66);
    }}
    html[data-theme="auto"] .health-score {{
      color: color-mix(in srgb, var(--ink) 94%, #fff 6%);
      text-shadow: 0 0 14px color-mix(in srgb, var(--accent) 42%, transparent);
    }}
    html[data-theme="auto"] .meter-badge,
    html[data-theme="auto"] .summary-pill {{
      border-color: color-mix(in srgb, var(--line) 92%, #fff 8%);
    }}
    html[data-theme="auto"] .health-ambient > span {{
      border-color: color-mix(in srgb, var(--line) 86%, transparent);
    }}
  }}
  .meter-track {{
    width:100%;
    height:12px;
    border-radius: 999px;
    overflow:hidden;
    border:1px solid color-mix(in srgb, var(--line) 55%, transparent);
    background:
      repeating-linear-gradient(
        90deg,
        var(--meter-track-a) 0 12px,
        var(--meter-track-b) 12px 16px
      );
  }}
  .meter-track {{
    position: relative;
  }}
  .meter-track::before {{
    content: "";
    position: absolute;
    inset: 0;
    opacity: .62;
    background:
      repeating-linear-gradient(to bottom, color-mix(in srgb, var(--line) 58%, transparent) 0 2px, transparent 2px 7px) 25% 0 / 1px 100% no-repeat,
      repeating-linear-gradient(to bottom, color-mix(in srgb, var(--line) 58%, transparent) 0 2px, transparent 2px 7px) 50% 0 / 1px 100% no-repeat,
      repeating-linear-gradient(to bottom, color-mix(in srgb, var(--line) 58%, transparent) 0 2px, transparent 2px 7px) 75% 0 / 1px 100% no-repeat;
    pointer-events: none;
  }}
  .meter-fill {{ height:100%; border-radius:999px; }}
  .meter-fill.teal {{
    background:
      repeating-linear-gradient(90deg, var(--meter-teal-a) 0 10px, var(--meter-teal-b) 10px 14px);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, #2d6f68 26%, transparent);
  }}
  .meter-fill.orange {{
    background:
      repeating-linear-gradient(90deg, var(--meter-orange-a) 0 10px, var(--meter-orange-b) 10px 14px);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, #8e4e29 24%, transparent);
  }}
  .meter-fill.ink {{
    background:
      repeating-linear-gradient(90deg, var(--meter-ink-a) 0 10px, var(--meter-ink-b) 10px 14px);
    box-shadow: inset 0 0 0 1px color-mix(in srgb, #3d4b61 22%, transparent);
  }}
  .meter-tip {{ margin-top:6px; font-size:11px; }}
  .summary-pills {{ display:flex; gap:7px; flex-wrap:wrap; margin-top:8px; }}
  .summary-pill {{
    border:1px solid color-mix(in srgb, var(--line) 78%, #fff 22%);
    border-radius:999px;
    padding:3px 9px;
    font-size:11px;
    background: color-mix(in srgb, var(--subtle-bg) 84%, transparent);
    box-shadow: inset 0 1px 0 color-mix(in srgb, #fff 30%, transparent);
  }}
  .issue-list {{
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 7px;
  }}
  .issue-list li {{
    border: 1px solid color-mix(in srgb, var(--line) 76%, #fff 24%);
    border-radius: 9px;
    padding: 7px 8px;
    background: color-mix(in srgb, var(--subtle-bg) 82%, transparent);
    line-height: 1.35;
    word-break: break-word;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }}
  .issue-main {{
    flex: 1;
    min-width: 0;
  }}
  .issue-link {{
    flex: 0 0 auto;
    border-radius: 999px;
    padding: 5px 9px;
    font-size: 11px;
    text-decoration: none;
  }}
  .quick-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(138px, 1fr));
    gap: 7px;
    margin-top: 8px;
  }}
  .quick-grid .btn {{
    justify-content: center;
    width: 100%;
    padding: 7px 10px;
    font-size: 12px;
    text-decoration: none;
  }}
  @media (max-width: 760px) {{
    .overview-top {{ grid-template-columns: 1fr; }}
    .health-headline {{ align-items:center; }}
    .health-score {{ font-size: 36px; }}
    .health-kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .mini-kpi {{ min-height: 76px; }}
    .health-ambient {{ grid-template-columns: repeat(8, minmax(0, 1fr)); gap: 5px; }}
    .quick-grid {{ grid-template-columns: 1fr; }}
  }}
</style>
<div class="overview-top">
  <section class="health-panel">
    <h2>{t("System Health", "系统健康")}</h2>
    <div class="health-headline">
      <div class="health-score">{health_score}</div>
      <div class="health-meta">
        <div class="health-state {health_tone}" title="{t('Composite score from channels/model/MCP/budget checks', '基于渠道/模型/MCP/预算检查综合得分')}">{escape(health_state_zh if zh else health_state_en)} · {risk_count}</div>
      </div>
    </div>
    <div class="health-scan"><span style="width:{max(0, min(100, health_score)):.1f}%"></span></div>
    <div class="health-kpis">
      <div class="mini-kpi">
        <div class="v">{ready_channel_count}/{len(enabled_channels)}</div>
        <div class="l">{t("Channels Ready", "渠道就绪")}</div>
      </div>
      <div class="mini-kpi">
        <div class="v">{len(endpoint_names)}</div>
        <div class="l">{t("Named Endpoints", "命名端点")}</div>
      </div>
      <div class="mini-kpi">
        <div class="v">{len(mcp_servers)}</div>
        <div class="l">{t("MCP Servers", "MCP 服务")}</div>
      </div>
      <div class="mini-kpi">
        <div class="v">{risk_count}</div>
        <div class="l">{t("Risk Items", "风险项")}</div>
      </div>
    </div>
    <div class="health-ambient" aria-hidden="true">
      <span></span><span></span><span></span><span></span><span></span><span></span>
      <span></span><span></span><span></span><span></span><span></span><span></span>
    </div>
  </section>
  <section class="card">
    <h2>{t("Runtime Checks", "运行检查")}</h2>
    <div class="side-stack">
      <div class="side-stat {model_stat_tone}" title="{escape(default_model_reason)}">
        <div class="k">{t("Default model check", "默认模型检查")}</div>
        <div class="v">{t("OK", "通过") if default_model_ok else t("FAIL", "失败")}</div>
        <div class="s" title="{escape(default_model_reason)}">{escape(default_model_reason[:44] + ('…' if len(default_model_reason) > 44 else ''))}</div>
      </div>
      <div class="side-stat {config_stat_tone}" title="{t('needs review if above zero', '大于 0 需要处理')}">
        <div class="k">{t("Config migration hints", "配置迁移提示")}</div>
        <div class="v">{len(config_hints)}</div>
        <div class="s">{t("needs review if above zero", "大于 0 需要处理")}</div>
      </div>
      <div class="side-stat {budget_stat_tone}" title="{t('runtime and context pressure', '运行时与上下文压力')}">
        <div class="k">{t("Budget alerts", "预算告警")}</div>
        <div class="v">{len(budget_alerts)}</div>
        <div class="s">{t("runtime and context pressure", "运行时与上下文压力")}</div>
      </div>
      <div class="side-stat {files_stat_tone}" title="{t('media + exports total files', 'media + exports 文件总数')}">
        <div class="k">{t("File Operations Overview", "文件处理总览")}</div>
        <div class="v">{media_count + export_count}</div>
        <div class="s">media {media_count} · exports {export_count}</div>
      </div>
    </div>
  </section>
</div>
<div class="grid cols-2 mt-14">
  <section class="card">
    <h2>{("主机资源监控" if zh else "Host Runtime Monitor")}</h2>
    <table>
      <tr><th>{t("CPU load(1m)", "CPU 负载(1m)")}</th><td>{escape(f"{load1:.2f}" if isinstance(load1, float) else "n/a")}</td></tr>
      <tr><th>{t("Memory used", "内存占用")}</th><td>{escape(f"{mem_used_percent:.1f}%" if isinstance(mem_used_percent, float) else "n/a")}</td></tr>
      <tr><th>{t("Disk used(/)", "磁盘占用(/)")}</th><td>{escape(f"{disk_used_percent:.1f}%" if isinstance(disk_used_percent, float) else "n/a")}</td></tr>
    </table>
    <div class="meter-grid">
      {meter_row(t("Memory", "内存"), f"{mem_used_percent:.1f}%" if isinstance(mem_used_percent, float) else "n/a", mem_used_percent, "teal")}
      {meter_row(t("CPU load ratio", "CPU 负载比例"), (f"load1={load1:.2f} / cores={int(cpu_cores)}" if isinstance(load1, float) and isinstance(cpu_cores, int) and cpu_cores > 0 else "n/a"), cpu_ratio_percent, "orange")}
      {meter_row(t("Disk", "磁盘"), f"{disk_used_percent:.1f}%" if isinstance(disk_used_percent, float) else "n/a", disk_used_percent, "ink")}
    </div>
  </section>
  <section class="card">
    <h2>{("上下文预算" if zh else "Context Budget")}</h2>
    <div class="meter-grid">
      {meter_row(t("history", "历史上下文"), f"{('已用' if zh else 'used')} {history_used_chars}/{history_chars} {t('chars', '字符')} · {('剩余' if zh else 'left')} {history_left_chars} · ≈ {history_tokens} {t('tokens', 'tokens')}", history_ratio, "teal")}
      {meter_row(t("memory", "记忆上下文"), f"{('已用' if zh else 'used')} {memory_used_chars}/{memory_chars} {t('chars', '字符')} · {('剩余' if zh else 'left')} {memory_left_chars} · ≈ {memory_tokens} {t('tokens', 'tokens')}", memory_ratio, "orange")}
      {meter_row(t("background", "背景上下文"), f"{('已用' if zh else 'used')} {background_used_chars}/{background_chars} {t('chars', '字符')} · {('剩余' if zh else 'left')} {background_left_chars} · ≈ {background_tokens} {t('tokens', 'tokens')}", background_ratio, "ink")}
    </div>
    <div class="summary-pills">
      <span class="summary-pill">{t("total context cap", "总上下文预算")}: <strong>{total_chars_budget}</strong> {t("chars", "字符")} ≈ <strong>{total_tokens_budget}</strong> {t("tokens", "tokens")}</span>
      <span class="summary-pill">{t("inline image cap", "内联图片上限")}: <strong>{inline_image_mb:.2f} MB</strong></span>
      <span class="summary-pill">{t("gc / cache", "gc / 缓存")}: <strong>gcEveryTurns={cfg.agents.defaults.gc_every_turns}, cache={cfg.agents.defaults.session_cache_max_entries}</strong></span>
    </div>
    <ul class="list small">
      {''.join(budget_rows) or f"<li>{t('No budget pressure detected.', '未检测到预算压力。')}</li>"}
    </ul>
  </section>
</div>
<div class="split mt-14">
  <section class="card">
    <h2>{t("Actionable Checks", "待处理检查项")}</h2>
    <ul class="issue-list small">
      {''.join(action_rows) or f"<li>{t('No blocking issue found.', '未发现阻塞问题。')}</li>"}
    </ul>
    <div class="quick-grid">
      <a class="btn subtle icon-btn" href="/chat" title="{'打开聊天' if zh else 'Open Chat'}">{icon_chat}{'聊天' if zh else 'Chat'}</a>
      <a class="btn subtle icon-btn" href="/channels" title="{t('Manage Channels', '管理聊天渠道')}">{icon_channels}{'渠道' if zh else 'Channels'}</a>
      <a class="btn subtle icon-btn" href="/endpoints" title="{t('Manage Models', '管理模型端点')}">{icon_model}{'模型' if zh else 'Models'}</a>
      <a class="btn subtle icon-btn" href="/mcp" title="{t('Manage MCP', '管理 MCP')}">{icon_mcp}MCP</a>
      <a class="btn subtle icon-btn" href="/media" title="{t('Manage Media', '管理媒体文件')}">{icon_media}{'文件' if zh else 'Files'}</a>
    </div>
  </section>
  <section class="card">
    <h2>{t("Runtime Paths & Counters", "运行目录与计数")}</h2>
    <table>
      <tr><th>{t("Config", "配置文件")}</th><td><code>{escape(str(cfg_path))}</code></td></tr>
      <tr><th>{t("Env main file", "Env 主文件")}</th><td><code>{escape(str(get_env_file()))}</code></td></tr>
      <tr><th>{t("Env directory", "Env 目录")}</th><td><code>{escape(str(get_env_dir()))}</code></td></tr>
      <tr><th>{t("Global skills", "全局技能目录")}</th><td><code>{escape(str(get_global_skills_path()))}</code></td></tr>
      <tr><th>{t("Workspace", "工作区")}</th><td><code>{escape(str(cfg.workspace_path))}</code></td></tr>
      <tr><th>{t("Gateway runtime", "Gateway 运行状态")}</th><td>{term("alive") if gateway_runtime_ready else term("not_ready")} ({escape(gateway_reason_zh if zh else gateway_reason_en)})</td></tr>
      <tr><th>{t("Gateway state file", "Gateway 状态文件")}</th><td><code>{escape(str(gateway_state_path))}</code></td></tr>
    </table>
  </section>
</div>
"""
    handler._send_html(200, handler._page(t("Dashboard", "仪表盘"), body, tab="/", msg=msg, err=err))


def render_channels(
    handler: Any,
    *,
    cfg_path: Path,
    gateway_runtime_status: GatewayRuntimeFn,
    msg: str = "",
    err: str = "",
) -> None:
    """Render the channels page (delegated to views_channels module)."""
    _render_channels_page(
        handler,
        cfg_path=cfg_path,
        gateway_runtime_status=gateway_runtime_status,
        msg=msg,
        err=err,
    )

def render_chat(handler: Any, *, msg: str = "", err: str = "", session_id: str = "default") -> None:
    """Render the web chat page."""
    _render_chat_page(handler, msg=msg, err=err, session_id=session_id)


def render_endpoints(handler: Any, *, msg: str = "", err: str = "") -> None:
    """Render the models/endpoints page (delegated to views_endpoints module)."""
    _render_endpoints_page(handler, msg=msg, err=err)


def render_mcp(handler: Any, *, collect_tool_policy_diagnostics: Callable[[Config, str], list[str]], msg: str = "", err: str = "") -> None:
    """Render MCP page (delegated to views_mcp module)."""
    _render_mcp_page(
        handler,
        collect_tool_policy_diagnostics=collect_tool_policy_diagnostics,
        msg=msg,
        err=err,
    )


def render_skills(handler: Any, *, msg: str = "", err: str = "") -> None:
    """Render skills page (delegated to views_skills module)."""
    _render_skills_page(handler, msg=msg, err=err)


def render_media(handler: Any, *, msg: str = "", err: str = "", media_page: int = 1, exports_page: int = 1) -> None:
    """Render media/files page (delegated to views_media module)."""
    _render_media_page(handler, msg=msg, err=err, media_page=media_page, exports_page=exports_page)
