"""Skills page renderer for Web UI."""

from __future__ import annotations

from typing import Any

from lunaeclaw.app.webui.catalog import (
    library_text as _library_text,
)
from lunaeclaw.app.webui.common import _pretty_json
from lunaeclaw.app.webui.html_utils import escape
from lunaeclaw.app.webui.i18n import ui_copy as _ui_copy
from lunaeclaw.app.webui.i18n import ui_term as _ui_term
from lunaeclaw.app.webui.icons import icon_svg
from lunaeclaw.app.webui.view_models import build_skill_library_rows, build_skill_rows


def render_skills(handler: Any, *, msg: str = "", err: str = "") -> None:
    """Render skills page."""
    cfg = handler._load_config()
    zh = handler._ui_lang == "zh-CN"

    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    def td(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn, track=False)

    def term(key: str) -> str:
        return _ui_term(handler._ui_lang, key)
    icon_add = icon_svg("add")
    icon_save = icon_svg("save")
    icon_import = icon_svg("import")

    skill_rows = build_skill_rows(cfg)
    total_skills = len(skill_rows)
    enabled_skills = sum(1 for s in skill_rows if not bool(s.get("disabled")))
    ready_skills = sum(1 for s in skill_rows if bool(s.get("available")) and not bool(s.get("disabled")))
    missing_dep_skills = sum(1 for s in skill_rows if (not bool(s.get("available"))) and not bool(s.get("disabled")))
    disabled_skills = max(0, total_skills - enabled_skills)
    built_in_skills = sum(1 for s in skill_rows if str(s.get("source") or "").lower() == "builtin")
    global_skills = sum(1 for s in skill_rows if str(s.get("source") or "").lower() == "global")
    other_skills = max(0, total_skills - built_in_skills - global_skills)
    ready_pct = (ready_skills / total_skills * 100.0) if total_skills > 0 else 0.0
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
    for lib_row in build_skill_library_rows(cfg, skill_rows):
        item = lib_row["item"]
        name = str(lib_row["name"])
        exists = bool(lib_row["exists"])
        skill_enabled = bool(lib_row["skill_enabled"])
        global_installed = bool(lib_row["global_installed"])
        health = lib_row["health"]
        health_label_map = {
            "ready": term("ready"),
            "disabled": term("disabled"),
            "missing_deps": t("missing deps", "缺少依赖"),
            "not_installed": term("not_installed"),
        }
        health_label = health_label_map.get(health["status"], health["label"])
        health_class = "ok" if health["status"] == "ready" else "off"
        if health["status"] == "not_installed":
            action_html = (
                f"""
<form method="post" class="row">
  <input type="hidden" name="action" value="install_skill_library">
  <input type="hidden" name="library_skill_id" value="{escape(str(item['id']))}">
  <button class="btn success icon-btn" type="submit">{icon_add}{t("Install to Global", "安装到全局")}</button>
</form>
"""
            )
        elif exists or global_installed:
            switch_title = "已启用，点击暂停" if (zh and skill_enabled) else "已暂停，点击启用" if zh else "Enabled, click to pause" if skill_enabled else "Paused, click to enable"
            switch_state = "on" if skill_enabled else "off"
            switch_label = "开" if (zh and skill_enabled) else "关" if zh else "ON" if skill_enabled else "OFF"
            action_html = (
                f"""
<form method="post" class="row">
  <input type="hidden" name="action" value="toggle_skill_from_library">
  <input type="hidden" name="skill_name" value="{escape(name)}">
  <button class="switch-btn {switch_state}" type="submit" title="{escape(switch_title)}"><span>{switch_label}</span></button>
</form>
"""
            )
        else:
            action_html = f"<span class='muted'>{term('no_action')}</span>"
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
<style>
  .skills-top-grid {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
    align-items: stretch;
  }}
  @media (max-width: 980px) {{
    .skills-top-grid {{
      grid-template-columns: 1fr;
    }}
  }}
  .skills-health {{
    border:1px solid color-mix(in srgb, var(--line) 78%, #fff 22%);
    border-radius: 12px;
    padding: 12px;
    background: linear-gradient(180deg, color-mix(in srgb, var(--card-strong) 88%, #fff 12%), color-mix(in srgb, var(--card) 90%, transparent));
  }}
  .health-head {{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:12px;
  }}
  .health-score {{
    font-size: 34px;
    line-height: 1;
    font-weight: 800;
    letter-spacing: .2px;
    color: color-mix(in srgb, var(--ink) 90%, #1e4977 10%);
  }}
  .health-progress {{
    margin-top: 6px;
    height: 10px;
    border-radius: 999px;
    border:1px solid color-mix(in srgb, var(--line) 55%, transparent);
    overflow: hidden;
    background:
      repeating-linear-gradient(
        90deg,
        var(--meter-track-a) 0 10px,
        var(--meter-track-b) 10px 14px
      );
  }}
  .health-progress span {{
    display:block;
    height:100%;
    background:
      repeating-linear-gradient(
        90deg,
        color-mix(in srgb, var(--meter-teal-a) 74%, #fff 26%) 0 10px,
        color-mix(in srgb, var(--meter-teal-b) 84%, #fff 16%) 10px 14px
      );
    box-shadow: inset 0 0 0 1px color-mix(in srgb, #2d6f68 26%, transparent);
  }}
  .health-meta strong {{
    font-size: 20px;
    line-height: 1;
    display: block;
  }}
  .health-meta span {{
    font-size: 12px;
    color: var(--muted);
  }}
  .health-grid {{
    margin-top: 12px;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }}
  .health-tile {{
    border:1px solid color-mix(in srgb, var(--line) 76%, #fff 24%);
    border-radius:10px;
    padding:8px 10px;
    background: color-mix(in srgb, var(--subtle-bg) 78%, transparent);
  }}
  .health-tile .v {{
    font-size: 18px;
    font-weight: 700;
    line-height: 1.1;
  }}
  .health-tile .k {{
    font-size: 11px;
    color: var(--muted);
    margin-top: 2px;
  }}
  .source-bars {{
    margin-top: 10px;
    display: grid;
    gap: 8px;
  }}
  .source-row {{
    display: grid;
    grid-template-columns: 72px 1fr auto;
    gap: 8px;
    align-items: center;
    font-size: 12px;
  }}
  .source-track {{
    height: 8px;
    border-radius: 999px;
    background:
      repeating-linear-gradient(
        90deg,
        var(--meter-track-a) 0 10px,
        var(--meter-track-b) 10px 14px
      );
    border:1px solid color-mix(in srgb, var(--line) 55%, transparent);
    overflow: hidden;
  }}
  .source-fill {{
    height: 100%;
    border-radius: 999px;
    background:
      repeating-linear-gradient(
        90deg,
        color-mix(in srgb, var(--meter-teal-a) 74%, #fff 26%) 0 10px,
        color-mix(in srgb, var(--meter-teal-b) 84%, #fff 16%) 10px 14px
      );
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--meter-teal-b) 35%, transparent);
  }}
</style>
<div class="skills-top-grid">
  <section class="card">
    <h2>{t("Skill Library (Local)", "技能库（本地）")}</h2>
    <form method="post">
      <input type="hidden" name="action" value="save_skills_enabled">
      <table>
        <tr><th></th><th>{t("Skill", "技能")}</th><th>{t("Source", "来源")}</th><th>{t("Status", "状态")}</th><th>{t("Requires", "依赖")}</th></tr>
        {''.join(rows_html) or f'<tr><td colspan="5" class="muted">{t("No skill found.", "未发现技能。")}</td></tr>'}
      </table>
      <div class="row mt-10"><button class="btn primary icon-btn" type="submit">{icon_save}{t("Save Skill Selection", "保存技能选择")}</button></div>
    </form>
  </section>
  <section class="card">
    <h2>{td("Skills Health", "技能健康总览")}</h2>
    <div class="skills-health">
      <div class="health-head">
        <div>
          <div class="health-score">{ready_pct:.0f}%</div>
          <div class="health-progress"><span style="width:{ready_pct:.1f}%"></span></div>
        </div>
        <div class="health-meta">
          <strong>{ready_skills}/{total_skills}</strong>
          <span>{td("ready and enabled", "可用且启用")}</span>
        </div>
      </div>
      <div class="health-grid">
        <div class="health-tile"><div class="v">{enabled_skills}</div><div class="k">{td("enabled", "已启用")}</div></div>
        <div class="health-tile"><div class="v">{disabled_skills}</div><div class="k">{td("disabled", "已禁用")}</div></div>
        <div class="health-tile"><div class="v">{missing_dep_skills}</div><div class="k">{td("missing deps", "缺少依赖")}</div></div>
        <div class="health-tile"><div class="v">{total_skills}</div><div class="k">{td("total", "总数")}</div></div>
      </div>
      <div class="source-bars">
        <div class="source-row">
          <span>{td("builtin", "内置")}</span>
          <span class="source-track"><span class="source-fill" style="width:{(built_in_skills / total_skills * 100.0) if total_skills else 0.0:.1f}%"></span></span>
          <span>{built_in_skills}</span>
        </div>
        <div class="source-row">
          <span>{td("global", "全局")}</span>
          <span class="source-track"><span class="source-fill" style="width:{(global_skills / total_skills * 100.0) if total_skills else 0.0:.1f}%"></span></span>
          <span>{global_skills}</span>
        </div>
        <div class="source-row">
          <span>{td("other", "其他")}</span>
          <span class="source-track"><span class="source-fill" style="width:{(other_skills / total_skills * 100.0) if total_skills else 0.0:.1f}%"></span></span>
          <span>{other_skills}</span>
        </div>
      </div>
    </div>
  </section>
</div>
<section class="card mt-14">
  <h2>{t("Skill Library", "技能库")}</h2>
  <table>
    <tr><th>{t("Name", "名称")}</th><th>{t("Description", "说明")}</th><th>{t("Health", "健康检查")}</th><th>{t("Action", "操作")}</th></tr>
    {''.join(lib_rows)}
  </table>
</section>
<section class="card mt-14">
  <h2>{t("Import Skill From URL", "从 URL 导入技能")}</h2>
  <form method="post" class="endpoint-fields">
    <input type="hidden" name="action" value="import_skill_from_url">
    <div class="field"><label>{t("Skill name", "技能名")}</label><input type="text" name="skill_name" placeholder="{t('e.g. my-skill', '例如：my-skill')}"></div>
    <div class="field"><label>{t("SKILL.md URL", "SKILL.md 链接")}</label><input type="text" name="skill_url" placeholder="{t('e.g. https://raw.githubusercontent.com/.../SKILL.md', '例如：https://raw.githubusercontent.com/.../SKILL.md')}"></div>
    <div class="field full"><button class="btn warn icon-btn" type="submit">{icon_import}{t("Import", "导入")}</button></div>
  </form>
</section>
<form method="post" class="card mt-14">
  <h2>{t("Skills JSON (Advanced)", "Skills JSON（高级）")}</h2>
  <input type="hidden" name="action" value="save_skills_json">
  <textarea class="tall-md" name="skills_json">{escape(skills_json)}</textarea>
  <div class="row mt-10"><button class="btn primary icon-btn" type="submit">{icon_save}{t("Save Skills JSON", "保存 Skills JSON")}</button></div>
</form>
"""
    handler._send_html(200, handler._page(t("Skills", "技能"), body, tab="/skills", msg=msg, err=err))
