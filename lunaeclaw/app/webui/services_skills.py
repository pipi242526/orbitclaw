"""Service helpers for WebUI skills mutations."""

from __future__ import annotations

from typing import Any

from orbitclaw.app.webui.common import _collect_skill_rows
from orbitclaw.platform.utils.helpers import get_global_skills_path


def localize_skill_install_reason(reason: str, *, zh: bool) -> str:
    text = str(reason or "").strip()
    if not text:
        return "未知错误" if zh else "unknown error"
    if text == "skill_name is required":
        return "skill_name 必填" if zh else text
    if text.startswith("built-in skill source not found: "):
        name = text.split(":", 1)[1].strip()
        return f"未找到内置技能源：{name}" if zh else text
    if text.startswith("skill already exists: "):
        name = text.split(":", 1)[1].strip()
        return f"技能已存在：{name}" if zh else text
    if text.startswith("installed skill: "):
        name = text.split(":", 1)[1].strip()
        return f"技能已安装：{name}" if zh else text
    return text


def enable_skill(cfg: Any, name: str) -> None:
    cfg.skills.disabled = [s for s in (cfg.skills.disabled or []) if s != name]


def toggle_skill(cfg: Any, name: str) -> bool:
    disabled_set = {s for s in (cfg.skills.disabled or []) if str(s).strip()}
    if name in disabled_set:
        disabled_set.discard(name)
        cfg.skills.disabled = sorted(disabled_set)
        return True
    disabled_set.add(name)
    cfg.skills.disabled = sorted(disabled_set)
    return False


def set_enabled_skills(cfg: Any, enabled_skills: set[str], *, known_skills: list[str] | None = None) -> None:
    all_known = known_skills or [row["name"] for row in _collect_skill_rows(cfg)]
    cfg.skills.disabled = [name for name in all_known if name not in enabled_skills]


def import_skill_markdown(cfg: Any, *, skill_name: str, content: str) -> None:
    skill_dir = get_global_skills_path() / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    enable_skill(cfg, skill_name)
