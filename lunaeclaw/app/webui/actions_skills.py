"""Skills POST action handlers for Web UI."""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from lunaeclaw.app.webui.catalog import find_skill_library_entry, install_skill_from_library
from lunaeclaw.app.webui.common import (
    _MAX_SKILL_IMPORT_BYTES,
    _collect_skill_rows,
    _is_private_or_local_host,
    _safe_json_object,
)
from lunaeclaw.app.webui.i18n import ui_copy as _ui_copy
from lunaeclaw.app.webui.services_skills import (
    enable_skill,
    import_skill_markdown,
    localize_skill_install_reason,
    set_enabled_skills,
    toggle_skill,
)
from lunaeclaw.platform.config.schema import SkillsConfig, ToolsConfig


def handle_post_skills(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /skills POST actions."""
    cfg = handler._load_config()
    action = handler._form_str(form, "action")
    zh = handler._ui_lang == "zh-CN"

    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    if action == "install_skill_library":
        entry_id = handler._form_str(form, "library_skill_id").strip()
        item = find_skill_library_entry(entry_id)
        if not item:
            raise ValueError(
                t("Unknown skill library entry: {entry_id}", "未知技能库条目: {entry_id}").format(entry_id=entry_id)
            )
        ok, reason = install_skill_from_library(str(item["name"]), overwrite=handler._form_bool(form, "overwrite_existing"))
        reason = localize_skill_install_reason(reason, zh=zh)
        if not ok:
            raise ValueError(reason)
        enable_skill(cfg, str(item["name"]))
        handler._save_config(cfg)
        handler._redirect("/skills", msg=reason)
        return

    if action == "enable_skill_from_library":
        name = handler._form_str(form, "skill_name").strip()
        if not name:
            raise ValueError(t("skill_name is required", "skill_name 必填"))
        enable_skill(cfg, name)
        handler._save_config(cfg)
        handler._redirect("/skills", msg=t("Skill enabled: {name}", "技能已启用: {name}").format(name=name))
        return

    if action == "toggle_skill_from_library":
        name = handler._form_str(form, "skill_name").strip()
        if not name:
            raise ValueError(t("skill_name is required", "skill_name 必填"))
        enabled_now = toggle_skill(cfg, name)
        msg = (
            t("Skill enabled: {name}", "技能已启用: {name}").format(name=name)
            if enabled_now
            else t("Skill paused: {name}", "技能已暂停: {name}").format(name=name)
        )
        if enabled_now:
            rows = {str(row.get("name") or ""): row for row in _collect_skill_rows(cfg)}
            current = rows.get(name)
            if current and not bool(current.get("available")):
                requires = str(current.get("requires") or "").strip()
                reason = requires or t("install required dependencies", "请安装缺失依赖")
                msg = t(
                    "Skill enabled but unavailable: {name} ({reason})",
                    "技能已启用但当前不可用: {name}（{reason}）",
                ).format(name=name, reason=reason)
        handler._save_config(cfg)
        handler._redirect("/skills", msg=msg)
        return

    if action == "import_skill_from_url":
        skill_name = handler._form_str(form, "skill_name").strip()
        skill_url = handler._form_str(form, "skill_url").strip()
        if not skill_name:
            raise ValueError(t("skill_name is required", "skill_name 必填"))
        parsed = urlparse(skill_url)
        if parsed.scheme != "https":
            raise ValueError(t("skill_url must use https://", "skill_url 必须使用 https://"))
        if not parsed.hostname:
            raise ValueError(t("skill_url must include host", "skill_url 必须包含主机名"))
        if _is_private_or_local_host(parsed.hostname):
            raise ValueError(t("skill_url host must be public", "skill_url 主机必须是公网地址"))
        try:
            req = urllib.request.Request(skill_url, headers={"User-Agent": "lunaeclaw-webui/0.1"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                content_type = (resp.headers.get("Content-Type") or "").lower()
                if content_type and "text" not in content_type and "markdown" not in content_type:
                    raise ValueError(t("skill_url must return text/markdown content", "skill_url 必须返回 text/markdown 内容"))
                content = resp.read(_MAX_SKILL_IMPORT_BYTES + 1)
                if len(content) > _MAX_SKILL_IMPORT_BYTES:
                    raise ValueError(t("skill file is too large (max 512KB)", "技能文件过大（最大 512KB）"))
                content = content.decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            raise ValueError(
                t("failed to fetch skill URL: {error}", "拉取 skill URL 失败: {error}").format(error=e)
            ) from e
        if "# " not in content and "SKILL" not in content.upper():
            raise ValueError(t("fetched content does not look like SKILL.md", "下载内容看起来不是 SKILL.md"))
        import_skill_markdown(cfg, skill_name=skill_name, content=content)
        handler._save_config(cfg)
        handler._redirect(
            "/skills",
            msg=t("Imported skill: {name}", "已导入技能: {name}").format(name=skill_name),
        )
        return

    if action == "save_skills_enabled":
        enabled_skills = {s.strip() for s in form.get("enabled_skill", []) if s.strip()}
        set_enabled_skills(cfg, enabled_skills)
        handler._save_config(cfg)
        handler._redirect("/skills", msg=t("Skill selection saved", "技能选择已保存"))
        return

    if action == "save_tools_json":
        data = _safe_json_object(handler._form_str(form, "tools_json"), "tools")
        cfg.tools = ToolsConfig.model_validate(data)
        handler._save_config(cfg)
        handler._redirect("/skills", msg=t("Tools config saved", "Tools 配置已保存"))
        return

    if action == "save_skills_json":
        data = _safe_json_object(handler._form_str(form, "skills_json"), "skills")
        cfg.skills = SkillsConfig.model_validate(data)
        handler._save_config(cfg)
        handler._redirect("/skills", msg=t("Skills config saved", "Skills 配置已保存"))
        return

    raise ValueError(t("Unsupported skills action", "不支持的技能操作"))
