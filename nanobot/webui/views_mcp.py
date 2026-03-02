"""MCP page renderer for Web UI."""

from __future__ import annotations

from html import escape
from typing import Any, Callable

from nanobot.config.schema import Config
from nanobot.webui.catalog import (
    MCP_LIBRARY as _MCP_LIBRARY,
)
from nanobot.webui.catalog import (
    evaluate_mcp_library_health,
)
from nanobot.webui.catalog import (
    library_text as _library_text,
)
from nanobot.webui.common import _mask_sensitive_url
from nanobot.webui.i18n import ui_copy as _ui_copy
from nanobot.webui.i18n import ui_term as _ui_term


def render_mcp(
    handler: Any,
    *,
    collect_tool_policy_diagnostics: Callable[[Config, str], list[str]],
    msg: str = "",
    err: str = "",
) -> None:
    """Render MCP management page."""
    cfg = handler._load_config()

    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    def term(key: str) -> str:
        return _ui_term(handler._ui_lang, key)
    mcp_rows = []
    for name in sorted(cfg.tools.mcp_servers.keys()):
        srv = cfg.tools.mcp_servers[name]
        target = _mask_sensitive_url(srv.url) if srv.url else f"{srv.command} {' '.join(srv.args or [])}".strip()
        enabled = (
            (not cfg.tools.mcp_enabled_servers)
            or (name in cfg.tools.mcp_enabled_servers)
        ) and (name not in (cfg.tools.mcp_disabled_servers or []))
        status_badge = (
            f'<span class="pill ok">{t("enabled", "已启用")}</span>'
            if enabled
            else f'<span class="pill off">{t("filtered", "已过滤")}</span>'
        )
        mcp_rows.append(
            f"<tr><td><code>{escape(name)}</code></td><td>{status_badge}</td><td class='mono'>{escape(target)}</td></tr>"
        )
    diag_warnings = collect_tool_policy_diagnostics(cfg, handler._ui_lang)
    lib_rows = []
    for item in _MCP_LIBRARY:
        sid = item["id"]
        health = evaluate_mcp_library_health(cfg, item)
        health_label_map = {
            "ready": term("ready"),
            "missing_env": term("missing_env"),
            "missing_command": term("missing_command"),
            "filtered": term("filtered"),
            "not_installed": term("not_installed"),
            "invalid": term("invalid"),
        }
        health_label = health_label_map.get(health["status"], health["label"])
        health_class = "ok" if health["status"] == "ready" else "off"
        hint = str(health.get("hint") or "").strip()
        if health["status"] == "missing_env":
            hint = t("missing env: {hint}", "缺少环境变量: {hint}").format(hint=hint)
        elif health["status"] == "missing_command":
            hint = t("missing command: {hint}", "缺少命令: {hint}").format(hint=hint)
        elif health["status"] == "not_installed":
            hint = term("install_from_library")
        elif health["status"] == "filtered":
            hint = term("installed_but_filtered")
        elif health["status"] == "ready":
            hint = term("enabled_hint")
        elif health["status"] == "invalid":
            hint = t("invalid catalog entry", "目录条目无效")
        lib_rows.append(
            f"""
<tr>
  <td><code>{escape(_library_text(item, 'name', handler._ui_lang))}</code></td>
  <td class="small">{escape(_library_text(item, 'desc', handler._ui_lang))}</td>
  <td><code>{escape(str(item['server_name']))}</code></td>
  <td><span class="pill {health_class}">{escape(str(health_label))}</span><div class="muted small">{escape(hint)}</div></td>
  <td>
    <form method="post" class="row">
      <input type="hidden" name="action" value="install_mcp_library">
      <input type="hidden" name="library_id" value="{escape(sid)}">
      <label class="small"><input type="checkbox" name="overwrite_existing"> {t("overwrite", "覆盖已有")}</label>
      <button class="btn primary" type="submit">{t("Install", "安装")}</button>
    </form>
  </td>
</tr>
"""
        )
    body = f"""
<div class="grid cols-2">
  <section class="card">
    <h2>{t("MCP Servers", "MCP 服务")}</h2>
    <table>
      <tr><th>{t("Server", "服务")}</th><th>{t("Status", "状态")}</th><th>{t("Target (masked)", "目标（脱敏）")}</th></tr>
      {''.join(mcp_rows) or f'<tr><td colspan="3" class="muted">{t("No MCP server configured.", "尚未配置 MCP 服务。")}</td></tr>'}
    </table>
    <form method="post" class="row" style="margin-top:10px">
      <input type="hidden" name="action" value="apply_recommended_mcp">
      <button class="btn warn" type="submit">{t("Apply Recommended (Exa + Docloader)", "应用推荐（Exa + Docloader）")}</button>
    </form>
  </section>
  <section class="card">
    <h2>{t("Privacy", "隐私说明")}</h2>
    <ul class="list small">
      <li>{t("Do not place raw API keys directly in JSON where possible.", "建议不要在 JSON 里直接写明文 API Key。")}</li>
      <li>{t("Prefer", "建议使用")} <code>${'{'}ENV_VAR{'}'}</code> + <code>~/.nanobot/.env</code>.</li>
      <li>{t("This page masks sensitive query values in MCP URLs.", "本页会自动脱敏 MCP URL 中的敏感参数。")}</li>
    </ul>
  </section>
</div>
<section class="card" style="margin-top:14px">
  <h2>{t("MCP Library", "MCP 库")}</h2>
  <table>
    <tr><th>{t("Name", "名称")}</th><th>{t("Description", "说明")}</th><th>{t("Server Key", "服务键")}</th><th>{t("Health", "健康检查")}</th><th>{t("Action", "操作")}</th></tr>
    {''.join(lib_rows)}
  </table>
</section>
<section class="card" style="margin-top:14px">
  <h2>{t("Install From Manifest URL", "从清单 URL 安装")}</h2>
  <form method="post" class="endpoint-fields">
    <input type="hidden" name="action" value="install_mcp_from_manifest_url">
    <div class="field full">
      <label>{t("Manifest URL (raw JSON list)", "清单 URL（raw JSON 列表）")}</label>
      <input type="text" name="manifest_url" placeholder="{t('e.g. https://raw.githubusercontent.com/.../mcp-library.json', '例如：https://raw.githubusercontent.com/.../mcp-library.json')}">
    </div>
    <div class="field">
      <label>{t("Entry ID", "条目 ID")}</label>
      <input type="text" name="entry_id" placeholder="{t('e.g. exa', '例如：exa')}">
    </div>
    <div class="field">
      <label><input type="checkbox" name="overwrite_existing"> {t("overwrite existing server", "覆盖已有同名服务")}</label>
    </div>
    <div class="field full">
      <button class="btn warn" type="submit">{t("Install Entry", "安装条目")}</button>
    </div>
  </form>
  <div class="muted">{t("Manifest format: [{id,name,server_name,config:{url|command,args,env}}]", "清单格式：[{id,name,server_name,config:{url|command,args,env}}]")}</div>
</section>
<section class="card" style="margin-top:14px">
  <h2>{t("Add Custom MCP Server", "添加自定义 MCP 服务")}</h2>
  <form method="post">
    <input type="hidden" name="action" value="save_custom_mcp">
    <div class="endpoint-fields">
      <div class="field"><label>{t("Server key", "服务键")}</label><input type="text" name="server_name" placeholder="{t('e.g. myserver', '例如：myserver')}"></div>
      <div class="field"><label>{t("Mode", "模式")}</label>
        <select name="mode">
          <option value="url">{t("HTTP URL", "HTTP 地址")}</option>
          <option value="stdio">{t("Stdio command", "标准输入输出命令")}</option>
        </select>
      </div>
      <div class="field full"><label>{t("URL (for HTTP mode)", "URL（HTTP 模式）")}</label><input type="text" name="url" placeholder="{t('e.g. https://example.com/mcp', '例如：https://example.com/mcp')}"></div>
      <div class="field"><label>{t("Command (for stdio mode)", "命令（stdio 模式）")}</label><input type="text" name="command" placeholder="{t('e.g. uvx', '例如：uvx')}"></div>
      <div class="field"><label>{t("Args (CSV, stdio mode)", "参数（CSV，stdio 模式）")}</label><input type="text" name="args_csv" placeholder="{t('e.g. package@latest, --flag', '例如：package@latest, --flag')}"></div>
      <div class="field full"><label>{t("Env JSON (optional)", "Env JSON（可选）")}</label><textarea name="env_json" style="min-height:120px">{{}}</textarea></div>
      <div class="field"><label><input type="checkbox" name="enable_now" checked> {t("add to enabled servers", "加入启用服务列表")}</label></div>
    </div>
    <div class="row"><button class="btn primary" type="submit">{t("Save MCP Server", "保存 MCP 服务")}</button></div>
  </form>
</section>
<section class="card" style="margin-top:14px">
  <h2>{t("Consistency Checks", "一致性检查")}</h2>
  <ul class="list small">
    {''.join(f'<li>{escape(item)}</li>' for item in diag_warnings) or f'<li>{t("No obvious conflict found.", "未发现明显冲突。")}</li>'}
  </ul>
</section>
"""
    handler._send_html(200, handler._page(t("MCP", "MCP"), body, tab="/mcp", msg=msg, err=err))
