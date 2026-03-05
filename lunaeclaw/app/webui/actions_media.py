"""Media/files POST action handlers for Web UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lunaeclaw.app.webui.i18n import ui_copy as _ui_copy
from lunaeclaw.app.webui.services import safe_positive_int
from lunaeclaw.platform.utils.helpers import get_exports_dir, get_media_dir


def _media_redirect_path(handler: Any, form: dict[str, list[str]]) -> str:
    media_page = safe_positive_int(handler._form_str(form, "media_page", "1"), default=1)
    exports_page = safe_positive_int(handler._form_str(form, "exports_page", "1"), default=1)
    return f"/media?media_page={media_page}&exports_page={exports_page}"


def _resolve_scope_root(cfg: Any, scope: str) -> Path:
    if scope == "media":
        return get_media_dir()
    if scope == "exports":
        return get_exports_dir((cfg.tools.files_hub.exports_dir or "").strip())
    raise ValueError(f"unsupported scope: {scope}")


def _normalize_delete_names(raw_names: list[str]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for raw in raw_names:
        name = str(raw or "").strip()
        if not name or name in seen:
            continue
        names.append(name)
        seen.add(name)
    return names


def _validate_name(name: str) -> bool:
    if not name or name in {".", ".."}:
        return False
    if "/" in name or "\\" in name:
        return False
    return Path(name).name == name


def _delete_from_scope(root: Path, names: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    deleted: list[str] = []
    missing: list[str] = []
    invalid: list[str] = []
    errors: list[str] = []
    root_resolved = root.resolve()

    for name in names:
        if not _validate_name(name):
            invalid.append(name)
            continue
        target = (root / name).resolve()
        try:
            target.relative_to(root_resolved)
        except ValueError:
            invalid.append(name)
            continue
        if not target.exists():
            missing.append(name)
            continue
        if not target.is_file():
            invalid.append(name)
            continue
        try:
            target.unlink()
            deleted.append(name)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    return deleted, missing, invalid, errors


def handle_post_media(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /media POST actions."""
    cfg = handler._load_config()
    action = handler._form_str(form, "action").strip()
    target_path = _media_redirect_path(handler, form)

    def t(en: str, zh_cn: str) -> str:
        return _ui_copy(handler._ui_lang, en, zh_cn)

    if action == "refresh":
        handler._redirect(target_path, msg=t("Refreshed.", "已刷新。"))
        return

    if action == "save_exports_dir":
        cfg.tools.files_hub.exports_dir = handler._form_str(form, "exports_dir").strip()
        handler._save_config(cfg)
        handler._redirect(target_path, msg=t("Exports directory saved.", "导出目录已保存。"))
        return

    if action == "save_exports_dir_default":
        cfg.tools.files_hub.exports_dir = ""
        handler._save_config(cfg)
        handler._redirect(target_path, msg=t("Exports directory reset to default.", "导出目录已恢复默认。"))
        return

    scope = handler._form_str(form, "scope", "media").strip().lower() or "media"
    root = _resolve_scope_root(cfg, scope)

    if action == "delete_selected":
        names = _normalize_delete_names([str(v) for v in form.get("selected_name", [])])
        if not names:
            raise ValueError(t("Select at least one file first.", "请先选择至少一个文件。"))
    elif action.startswith("delete_one:"):
        names = _normalize_delete_names([action.split(":", 1)[1]])
    else:
        raise ValueError(t("Unsupported media action", "不支持的媒体操作"))

    deleted, missing, invalid, errors = _delete_from_scope(root, names)
    if not deleted and (missing or invalid or errors):
        problem = errors[0] if errors else (invalid[0] if invalid else missing[0])
        raise ValueError(
            t("No files deleted: {problem}", "未删除任何文件：{problem}").format(problem=problem)
        )

    scope_label = t("media", "媒体目录") if scope == "media" else t("exports", "导出目录")
    msg = t("Deleted {count} file(s) from {scope}.", "已从{scope}删除 {count} 个文件。").format(
        count=len(deleted),
        scope=scope_label,
    )
    extras: list[str] = []
    if missing:
        extras.append(t("missing {count}", "缺失 {count}").format(count=len(missing)))
    if invalid:
        extras.append(t("invalid {count}", "无效 {count}").format(count=len(invalid)))
    if errors:
        extras.append(t("errors {count}", "失败 {count}").format(count=len(errors)))
    if extras:
        msg = f"{msg} ({', '.join(extras)})"
    handler._redirect(target_path, msg=msg)
