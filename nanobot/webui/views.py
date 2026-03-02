"""WebUI page renderers extracted from the HTTP handler.

The renderers accept the request handler instance so we keep behavior unchanged
while reducing coupling/size in server.py.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path
from typing import Any, Callable

from nanobot.config.loader import load_config
from nanobot.config.schema import Config
from nanobot.utils.budget import (
    collect_runtime_budget_alerts,
)
from nanobot.utils.budget import (
    estimate_tokens_from_chars as _estimate_tokens_from_chars,
)
from nanobot.utils.budget import (
    read_host_resource_snapshot as _read_host_resource_snapshot,
)
from nanobot.utils.helpers import (
    get_env_dir,
    get_env_file,
    get_exports_dir,
    get_global_skills_path,
)
from nanobot.webui.common import (
    _CHANNEL_QUICK_SPECS,
    _check_default_model_ref,
    _collect_skill_rows,
    _list_media_rows,
    _list_store_rows,
)
from nanobot.webui.diagnostics import collect_config_migration_hints
from nanobot.webui.i18n import ui_copy as _ui_copy
from nanobot.webui.i18n import ui_term as _ui_term
from nanobot.webui.views_channels import render_channels as _render_channels_page
from nanobot.webui.views_endpoints import render_endpoints as _render_endpoints_page
from nanobot.webui.views_mcp import render_mcp as _render_mcp_page
from nanobot.webui.views_media import render_media as _render_media_page
from nanobot.webui.views_skills import render_skills as _render_skills_page

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
    channels_data = cfg.channels.model_dump()
    channel_names = [str(x["id"]) for x in _CHANNEL_QUICK_SPECS]
    enabled_channels = [name for name in channel_names if bool((channels_data.get(name) or {}).get("enabled"))]
    endpoint_names = sorted(cfg.providers.endpoints.keys())
    mcp_servers = cfg.tools.mcp_servers or {}
    skills_rows = _collect_skill_rows(cfg)
    unavailable_skills = [s for s in skills_rows if (not s["available"]) and (not s["disabled"])]
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
    budget_alerts = collect_runtime_budget_alerts(cfg_resolved, snapshot)
    penalty = (len(issues) * 15) + sum(18 if a.get("severity") == "error" else 8 for a in budget_alerts)
    health_score = max(0, 100 - penalty)
    ready_channel_count = max(0, len(enabled_channels) - len({x.split(":", 1)[0] for x in channel_issues}))
    load1 = snapshot.get("load1")
    mem_used_percent = snapshot.get("mem_used_percent")
    disk_used_percent = snapshot.get("disk_used_percent")

    history_chars = int(cfg.agents.defaults.max_history_chars)
    memory_chars = int(cfg.agents.defaults.max_memory_context_chars)
    background_chars = int(cfg.agents.defaults.max_background_context_chars)
    total_chars_budget = max(0, history_chars + memory_chars + background_chars)
    total_tokens_budget = _estimate_tokens_from_chars(total_chars_budget)
    inline_image_mb = max(0.0, cfg.agents.defaults.max_inline_image_bytes / 1024 / 1024)

    action_rows = []
    for item in issues[:6]:
        if item.startswith("default model:"):
            action_rows.append(
                f"<li>{escape(item)} · <a class='mono' href='/endpoints'>{t('fix in Models & APIs', '去模型与接口修复')}</a></li>"
            )
        elif item.startswith("endpoint `"):
            action_rows.append(
                f"<li>{escape(item)} · <a class='mono' href='/endpoints'>{t('open endpoint and resave models', '打开端点后重新保存 models')}</a></li>"
            )
        elif "exa_mcp" in item:
            action_rows.append(
                f"<li>{escape(item)} · <a class='mono' href='/mcp'>{t('fix in MCP page', '去 MCP 页面修复')}</a></li>"
            )
        elif item.startswith("config:"):
            action_rows.append(
                f"<li>{escape(item)} · <a class='mono' href='/'>{t('review config migration hints and resave related page', '查看配置迁移提示后到对应页面重存')}</a></li>"
            )
        elif item.startswith("gateway runtime:"):
            action_rows.append(
                f"<li>{escape(item)} · <a class='mono' href='/'>{t('ensure gateway uses same NANOBOT_DATA_DIR and is running', '确保 gateway 使用相同 NANOBOT_DATA_DIR 并处于运行中')}</a></li>"
            )
        else:
            action_rows.append(
                f"<li>{escape(item)} · <a class='mono' href='/channels'>{t('fix in Channels page', '去渠道页面修复')}</a></li>"
            )
    for alert in budget_alerts[:4]:
        severity = str(alert.get("severity") or "warn").upper()
        message = str(alert.get("message") or "").strip()
        suggestion = str(alert.get("suggestion") or "").strip()
        if not message:
            continue
        action_rows.append(
            f"<li>[{escape(severity)}] {escape(message)}"
            f"{f' · <span class=mono>{escape(suggestion)}</span>' if suggestion else ''}"
            f" · <a class='mono' href='/endpoints'>{t('tune budgets', '调整预算')}</a></li>"
        )
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
    body = f"""
<div class="grid cols-3">
  <section class="card">
    <h2>{t("Health Score", "健康分")}</h2>
    <div class="kpi">{health_score}</div>
    <div class="muted">{t("Based on model/channels/MCP runtime checks", "基于模型/渠道/MCP 运行时检查")}</div>
  </section>
  <section class="card">
    <h2>{t("Channels Ready", "渠道就绪")}</h2>
    <div class="kpi">{ready_channel_count}/{len(enabled_channels)}</div>
    <div class="muted">{escape(', '.join(enabled_channels) or t('none enabled', '未启用'))}</div>
  </section>
  <section class="card">
    <h2>{t("Named Endpoints", "命名端点")}</h2>
    <div class="kpi">{len(endpoint_names)}</div>
    <div class="muted">{escape(', '.join(endpoint_names[:6]) or t('none', '未配置'))}</div>
  </section>
</div>
<div class="grid cols-2" style="margin-top:14px">
  <section class="card">
    <h2>{t("Resource Radar", "资源雷达")}</h2>
    <table>
      <tr><th>{t("CPU load(1m)", "CPU 负载(1m)")}</th><td>{escape(f"{load1:.2f}" if isinstance(load1, float) else "n/a")}</td></tr>
      <tr><th>{t("Memory used", "内存占用")}</th><td>{escape(f"{mem_used_percent:.1f}%" if isinstance(mem_used_percent, float) else "n/a")}</td></tr>
      <tr><th>{t("Disk used(/)", "磁盘占用(/)")}</th><td>{escape(f"{disk_used_percent:.1f}%" if isinstance(disk_used_percent, float) else "n/a")}</td></tr>
    </table>
    <div class="muted">
      {t("This is a lightweight runtime snapshot from the current host.", "这是当前主机的轻量运行快照。")}
    </div>
  </section>
  <section class="card">
    <h2>{t("Token Budget Radar", "Token 预算雷达")}</h2>
    <table>
      <tr><th>{t("history", "历史上下文")}</th><td>{history_chars} {t("chars", "字符")} ≈ { _estimate_tokens_from_chars(history_chars) } {t("tokens", "tokens")}</td></tr>
      <tr><th>{t("memory", "记忆上下文")}</th><td>{memory_chars} {t("chars", "字符")} ≈ { _estimate_tokens_from_chars(memory_chars) } {t("tokens", "tokens")}</td></tr>
      <tr><th>{t("background", "背景上下文")}</th><td>{background_chars} {t("chars", "字符")} ≈ { _estimate_tokens_from_chars(background_chars) } {t("tokens", "tokens")}</td></tr>
      <tr><th>{t("total context cap", "总上下文预算")}</th><td>{total_chars_budget} {t("chars", "字符")} ≈ {total_tokens_budget} {t("tokens", "tokens")}</td></tr>
      <tr><th>{t("inline image cap", "内联图片上限")}</th><td>{inline_image_mb:.2f} MB</td></tr>
      <tr><th>{t("gc / cache", "gc / 缓存")}</th><td>gcEveryTurns={cfg.agents.defaults.gc_every_turns}, cache={cfg.agents.defaults.session_cache_max_entries}</td></tr>
    </table>
    <div class="muted" style="margin-top:8px">{t("Budget alerts", "预算告警")}: {len(budget_alerts)}</div>
    <ul class="list small">
      {''.join(budget_rows) or f"<li>{t('No budget pressure detected.', '未检测到预算压力。')}</li>"}
    </ul>
    <div class="muted">{t("Estimation uses ~1 token per 3 chars (mixed text).", "估算按约 1 token ≈ 3 chars（中英混合粗估）。")}</div>
  </section>
</div>
<div class="split" style="margin-top:14px">
  <section class="card">
    <h2>{t("Actionable Checks", "待处理检查项")}</h2>
    <ul class="list small">
      {''.join(action_rows) or f"<li>{t('No blocking issue found.', '未发现阻塞问题。')}</li>"}
    </ul>
    <div class="row" style="margin-top:10px">
      <a class="btn subtle icon-btn" href="/channels"><span aria-hidden="true">💬</span>{t("Manage Channels", "管理聊天渠道")}</a>
      <a class="btn subtle icon-btn" href="/endpoints"><span aria-hidden="true">🧠</span>{t("Manage Models", "管理模型端点")}</a>
      <a class="btn subtle icon-btn" href="/mcp"><span aria-hidden="true">🧩</span>{t("Manage MCP", "管理 MCP")}</a>
      <a class="btn subtle icon-btn" href="/media"><span aria-hidden="true">🗂</span>{t("Manage Media", "管理媒体文件")}</a>
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
      <tr><th>{t("Media files", "媒体文件数")}</th><td>{media_count}</td></tr>
      <tr><th>{t("Export files", "导出文件数")}</th><td>{export_count}</td></tr>
      <tr><th>{t("Default model check", "默认模型检查")}</th><td>{t("OK", "通过") if default_model_ok else t("FAIL", "失败")} ({escape(default_model_reason)})</td></tr>
      <tr><th>{t("Config migration hints", "配置迁移提示")}</th><td>{len(config_hints)}</td></tr>
      <tr><th>{t("Budget alerts", "预算告警")}</th><td>{len(budget_alerts)}</td></tr>
      <tr><th>{t("Unavailable skills", "不可用技能")}</th><td>{len(unavailable_skills)}</td></tr>
      <tr><th>{t("MCP servers", "MCP 服务数")}</th><td>{len(mcp_servers)} ({len(cfg.tools.mcp_enabled_servers or [])} {t("allowlisted", "白名单启用")})</td></tr>
      <tr><th>{t("Gateway runtime", "Gateway 运行状态")}</th><td>{term("alive") if gateway_runtime_ready else term("not_ready")} ({escape(gateway_reason_zh if zh else gateway_reason_en)})</td></tr>
      <tr><th>{t("Gateway state file", "Gateway 状态文件")}</th><td><code>{escape(str(gateway_state_path))}</code></td></tr>
    </table>
    <div class="muted">{t("For full diagnostics, run", "更详细诊断建议使用")} <code>nanobot doctor</code></div>
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
