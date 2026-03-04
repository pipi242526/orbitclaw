"""Unified file hub tool for chat attachments and generated exports."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from lunaeclaw.capabilities.tools.base import Tool
from lunaeclaw.platform.utils.helpers import get_exports_dir, get_media_dir


def _display_name(name: str) -> str:
    # Telegram/Discord saved files may use prefixes like "<id>_<original-name.ext>".
    if "_" in name:
        prefix, rest = name.split("_", 1)
        if prefix and len(prefix) >= 8 and rest:
            return rest
    return name


class _BaseFilesTool(Tool):
    _SCOPES: dict[str, Path]

    @staticmethod
    def _dump(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)

    def _resolve_scope_dir(self, scope: str | None) -> tuple[str, Path] | tuple[None, None]:
        key = (scope or "").strip().lower() or "media"
        if key not in self._SCOPES:
            return None, None
        return key, self._SCOPES[key]

    @staticmethod
    def _iter_files(root: Path) -> list[Path]:
        if not root.exists():
            return []
        return sorted(
            [p for p in root.iterdir() if p.is_file()],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    @staticmethod
    def _row(p: Path) -> dict[str, Any]:
        st = p.stat()
        return {
            "name": p.name,
            "displayName": _display_name(p.name),
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            "path": str(p),
        }

    def _list_scope(self, root: Path, limit: int) -> list[dict[str, Any]]:
        return [self._row(p) for p in self._iter_files(root)[: max(1, min(limit or 50, 200))]]

    def _delete_names(self, root: Path, names: list[str]) -> dict[str, Any]:
        deleted: list[str] = []
        missing: list[str] = []
        errors: list[dict[str, str]] = []
        for name in names:
            if "/" in name or "\\" in name or name in {".", ".."}:
                errors.append({"name": name, "error": "invalid_name"})
                continue
            p = (root / name).resolve()
            try:
                p.relative_to(root.resolve())
            except ValueError:
                errors.append({"name": name, "error": "outside_scope_dir"})
                continue
            if not p.exists():
                missing.append(name)
                continue
            if not p.is_file():
                errors.append({"name": name, "error": "not_a_file"})
                continue
            try:
                p.unlink()
                deleted.append(name)
            except Exception as e:
                errors.append({"name": name, "error": str(e)})
        return {"deleted": deleted, "missing": missing, "errors": errors}


class FilesHubTool(_BaseFilesTool):
    """List/delete files in lunaeclaw managed directories (media/exports)."""

    name = "files_hub"
    description = "List or delete files in lunaeclaw stores (media attachments, exports)."
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "delete"]},
            "scope": {
                "type": "string",
                "enum": ["media", "exports"],
                "description": "File store scope. media = uploaded attachments, exports = generated outputs.",
                "default": "media",
            },
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File names to delete (exact names from list). Only used when action=delete.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "description": "Max items to list."},
        },
        "required": ["action"],
    }

    def __init__(self, media_dir: Path | None = None, exports_dir: Path | None = None):
        self._SCOPES = {
            "media": (media_dir or get_media_dir()).expanduser(),
            "exports": (exports_dir or get_exports_dir()).expanduser(),
        }

    async def execute(
        self,
        action: str,
        scope: str = "media",
        names: list[str] | None = None,
        limit: int = 50,
        **kwargs: Any,
    ) -> str:
        act = (action or "").strip().lower()
        scope_key, root = self._resolve_scope_dir(scope)
        if not scope_key or root is None:
            return self._dump({"error": "unsupported_scope", "supportedScopes": list(self._SCOPES.keys())})

        if act == "list":
            rows = self._list_scope(root, limit)
            return self._dump(
                {
                    "action": "list",
                    "scope": scope_key,
                    "dir": str(root),
                    "count": len(rows),
                    "files": rows,
                }
            )

        if act == "delete":
            req = [str(x).strip() for x in (names or []) if str(x).strip()]
            if not req:
                return self._dump(
                    {
                        "error": "missing_names",
                        "hint": f"Call files_hub with action=delete, scope={scope_key}, names=[...] from a prior list result.",
                    }
                )
            result = self._delete_names(root, req)
            return self._dump({"action": "delete", "scope": scope_key, "dir": str(root), **result})

        return self._dump({"error": "unsupported_action", "supported": ["list", "delete"]})

