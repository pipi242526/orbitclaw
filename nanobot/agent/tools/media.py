"""Media file management tool for downloaded attachments (~/.nanobot/media)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.utils.helpers import get_media_dir


def _display_name(name: str) -> str:
    # Telegram/Discord saved files may use prefixes like "<id>_<original-name.ext>".
    if "_" in name:
        prefix, rest = name.split("_", 1)
        if prefix and len(prefix) >= 8 and rest:
            return rest
    return name


class MediaFilesTool(Tool):
    """List and delete downloaded media files in the global media directory."""

    name = "media_files"
    description = "List or delete downloaded chat attachments in ~/.nanobot/media."
    parameters = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["list", "delete"]},
            "names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File names to delete (exact names from list). Only used when action=delete.",
            },
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "description": "Max items to list."},
        },
        "required": ["action"],
    }

    def __init__(self, media_dir: Path | None = None):
        self._media_dir = (media_dir or get_media_dir()).expanduser()

    @staticmethod
    def _dump(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)

    def _iter_files(self) -> list[Path]:
        if not self._media_dir.exists():
            return []
        return sorted(
            [p for p in self._media_dir.iterdir() if p.is_file()],
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

    async def execute(
        self,
        action: str,
        names: list[str] | None = None,
        limit: int = 50,
        **kwargs: Any,
    ) -> str:
        act = (action or "").strip().lower()
        if act == "list":
            rows = [self._row(p) for p in self._iter_files()[: max(1, min(limit or 50, 200))]]
            return self._dump({"action": "list", "mediaDir": str(self._media_dir), "count": len(rows), "files": rows})

        if act == "delete":
            req = [str(x).strip() for x in (names or []) if str(x).strip()]
            if not req:
                return self._dump({"error": "missing_names", "hint": "Call media_files with action=delete and names=[...] from a prior list result."})
            deleted: list[str] = []
            missing: list[str] = []
            errors: list[dict[str, str]] = []
            for name in req:
                # delete by exact basename only, prevent traversal
                if "/" in name or "\\" in name or name in {".", ".."}:
                    errors.append({"name": name, "error": "invalid_name"})
                    continue
                p = (self._media_dir / name).resolve()
                try:
                    p.relative_to(self._media_dir.resolve())
                except ValueError:
                    errors.append({"name": name, "error": "outside_media_dir"})
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
            return self._dump(
                {
                    "action": "delete",
                    "mediaDir": str(self._media_dir),
                    "deleted": deleted,
                    "missing": missing,
                    "errors": errors,
                }
            )

        return self._dump({"error": "unsupported_action", "supported": ["list", "delete"]})

