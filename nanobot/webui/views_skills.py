"""Skills page renderer for Web UI."""

from __future__ import annotations

from html import escape
from typing import Any

from nanobot.utils.helpers import get_global_skills_path
from nanobot.webui.catalog import (
    SKILL_LIBRARY as _SKILL_LIBRARY,
)
from nanobot.webui.catalog import (
    evaluate_skill_library_health,
)
from nanobot.webui.catalog import (
    library_text as _library_text,
)
from nanobot.webui.common import _collect_skill_rows, _pretty_json
from nanobot.webui.i18n import ui_copy as _ui_copy
from nanobot.webui.i18n import ui_term as _ui_term


def render_skills(handler: Any, *, msg: str = "", err: str = "") -> None:
    """Render skills page."""
    cfg = handler._load_config()

    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    def term(key: str) -> str:
        return _ui_term(handler._ui_lang, key)

    skill_rows = _collect_skill_rows(cfg)
    known_skills = {str(s["name"]) for s in skill_rows}
    rows_html = []
    for s in skill_rows:
        badge = (
            f'<span class="pill ok">{t("available", "可用")}</span>'
            if s["available"]
            else f'<span class="pill off">{t("missing deps", "缺少依赖")}</span>'
        )
        if s["disabled"]:
            badge = f'<span class="pill">{term("disabled")}</span>'
        rows_html.append(
            f"""
<tr>
  <td><input type="checkbox" name="enabled_skill" value="{escape(s['name'])}" {"checked" if not s['disabled'] else ""}></td>
  <td><code>{escape(s['name'])}</code></td>
  <td>{escape(s['source'])}</td>
  <td>{badge}</td>
  <td class="small">{escape(s['requires'])}</td>
</tr>
"""
        )
    lib_rows = []
    for item in _SKILL_LIBRARY:
        name = str(item["name"])
        exists = name in known_skills
        global_skill_file = get_global_skills_path() / name / "SKILL.md"
        global_installed = global_skill_file.exists()
        health = evaluate_skill_library_health(cfg, item, skill_rows)
        health_label_map = {
            "ready": term("ready"),
            "disabled": term("disabled"),
            "missing_deps": t("missing deps", "缺少依赖"),
            "not_installed": term("not_installed"),
        }
        health_label = health_label_map.get(health["status"], health["label"])
        health_class = "ok" if health["status"] == "ready" else "off"
        action_parts: list[str] = []
        if not global_installed:
            action_parts.append(
                f"""
<form method="post" class="row">
  <input type="hidden" name="action" value="install_skill_library">
  <input type="hidden" name="library_skill_id" value="{escape(str(item['id']))}">
  <button class="btn primary" type="submit">{t("Install to Global", "安装到全局")}</button>
</form>
"""
            )
        if exists:
            action_parts.append(
                f"""
<form method="post" class="row">
  <input type="hidden" name="action" value="enable_skill_from_library">
  <input type="hidden" name="skill_name" value="{escape(name)}">
  <button class="btn" type="submit">{t("Enable", "启用")}</button>
</form>
"""
            )
        action_html = "".join(action_parts) or f"<span class='muted'>{term('no_action')}</span>"
        raw_hint = str(health.get("hint") or "").strip()
        hint = ""
        if health["status"] == "not_installed":
            hint = t("install or import skill", "请先安装或导入技能")
        elif health["status"] == "disabled":
            hint = t("enable in skill selection", "可在技能选择里启用")
        elif health["status"] == "missing_deps":
            hint = (
                t("requires: {hint}", "依赖: {hint}").format(hint=raw_hint)
                if raw_hint
                else t("install missing dependencies", "请安装缺失依赖")
            )
        elif health["status"] == "ready":
            hint = t("enabled", "已启用")
        elif raw_hint:
            hint = raw_hint
        if not global_installed:
            suffix = t("global copy missing", "全局目录未安装")
            hint = f"{hint}; {suffix}" if hint else suffix
        lib_rows.append(
            f"""
<tr>
  <td><code>{escape(name)}</code></td>
  <td class="small">{escape(_library_text(item, 'desc', handler._ui_lang))}</td>
  <td><span class="pill {health_class}">{escape(str(health_label))}</span><div class="muted small">{escape(hint)}</div></td>
  <td>{action_html}</td>
</tr>
"""
        )
    skills_json = _pretty_json(cfg.skills.model_dump(by_alias=True))
    body = f"""
<div class="grid cols-2">
  <section class="card">
    <h2>{t("Skill Library (Local)", "技能库（本地）")}</h2>
    <form method="post">
      <input type="hidden" name="action" value="save_skills_enabled">
      <table>
        <tr><th></th><th>{t("Skill", "技能")}</th><th>{t("Source", "来源")}</th><th>{t("Status", "状态")}</th><th>{t("Requires", "依赖")}</th></tr>
        {''.join(rows_html) or f'<tr><td colspan="5" class="muted">{t("No skill found.", "未发现技能。")}</td></tr>'}
      </table>
      <div class="row" style="margin-top:10px"><button class="btn primary" type="submit">{t("Save Skill Selection", "保存技能选择")}</button></div>
    </form>
  </section>
  <section class="card">
    <h2>{t("Skill Notes", "技能说明")}</h2>
    <ul class="list small">
      <li>{t("Keep only skills you actually use to reduce startup checks and noise.", "只保留常用技能，可减少启动检查和日志噪音。")}</li>
      <li>{t("Missing-dependency skills can stay disabled by default.", "缺少依赖的技能建议默认禁用。")}</li>
      <li>{t("Use the URL import box below if you want to add third-party skills.", "需要三方技能时，可使用下方 URL 导入。")}</li>
    </ul>
  </section>
</div>
<section class="card" style="margin-top:14px">
  <h2>{t("Skill Library", "技能库")}</h2>
  <table>
    <tr><th>{t("Name", "名称")}</th><th>{t("Description", "说明")}</th><th>{t("Health", "健康检查")}</th><th>{t("Action", "操作")}</th></tr>
    {''.join(lib_rows)}
  </table>
</section>
<section class="card" style="margin-top:14px">
  <h2>{t("Import Skill From URL", "从 URL 导入技能")}</h2>
  <form method="post" class="endpoint-fields">
    <input type="hidden" name="action" value="import_skill_from_url">
    <div class="field"><label>{t("Skill name", "技能名")}</label><input type="text" name="skill_name" placeholder="{t('e.g. my-skill', '例如：my-skill')}"></div>
    <div class="field"><label>{t("SKILL.md URL", "SKILL.md 链接")}</label><input type="text" name="skill_url" placeholder="{t('e.g. https://raw.githubusercontent.com/.../SKILL.md', '例如：https://raw.githubusercontent.com/.../SKILL.md')}"></div>
    <div class="field full"><button class="btn warn" type="submit">{t("Import", "导入")}</button></div>
  </form>
</section>
<form method="post" class="card" style="margin-top:14px">
  <h2>{t("Skills JSON (Advanced)", "Skills JSON（高级）")}</h2>
  <input type="hidden" name="action" value="save_skills_json">
  <textarea name="skills_json" style="min-height:360px">{escape(skills_json)}</textarea>
  <div class="row" style="margin-top:10px"><button class="btn primary" type="submit">{t("Save Skills JSON", "保存 Skills JSON")}</button></div>
</form>
"""
    handler._send_html(200, handler._page(t("Skills", "技能"), body, tab="/skills", msg=msg, err=err))
