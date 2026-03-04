"""Unified export tool for common output formats."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lunaeclaw.capabilities.tools.base import Tool
from lunaeclaw.platform.utils.helpers import get_exports_dir


class ExportFileTool(Tool):
    """Export generated content to the configured exports directory."""

    name = "export_file"
    description = "Write generated content to exports dir as txt/md/json/docx."
    parameters = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Target file name (e.g., report.txt, notes.md, result.json, summary.docx).",
            },
            "content": {"type": "string", "description": "Text content to export."},
            "format": {
                "type": "string",
                "enum": ["txt", "md", "json", "docx"],
                "description": "Output format. If omitted, inferred from filename extension.",
            },
            "overwrite": {"type": "boolean", "description": "Whether to overwrite existing file.", "default": True},
        },
        "required": ["filename", "content"],
    }

    def __init__(self, exports_dir: Path | None = None):
        self._exports_dir = (exports_dir or get_exports_dir()).expanduser().resolve()

    @staticmethod
    def _dump(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False)

    def _safe_target(self, filename: str) -> tuple[Path | None, str | None]:
        name = (filename or "").strip()
        if not name:
            return None, "empty_filename"
        if name in {".", ".."} or "/" in name or "\\" in name:
            return None, "invalid_filename"
        target = (self._exports_dir / name).resolve()
        try:
            target.relative_to(self._exports_dir)
        except ValueError:
            return None, "outside_exports_dir"
        return target, None

    @staticmethod
    def _infer_format(target: Path, explicit: str | None) -> str:
        fmt = (explicit or "").strip().lower()
        if fmt:
            return fmt
        ext = target.suffix.lower().lstrip(".")
        return ext or "txt"

    def _write_docx(self, target: Path, content: str) -> tuple[bool, str | None]:
        try:
            from docx import Document  # type: ignore
        except Exception:
            return False, "python-docx not installed"
        doc = Document()
        for line in content.splitlines() or [content]:
            doc.add_paragraph(line)
        doc.save(target)
        return True, None

    async def execute(
        self,
        filename: str,
        content: str,
        format: str | None = None,
        overwrite: bool = True,
        **kwargs: Any,
    ) -> str:
        target, err = self._safe_target(filename)
        if err or target is None:
            return self._dump({"error": err or "invalid_filename"})

        fmt = self._infer_format(target, format)
        if fmt not in {"txt", "md", "json", "docx"}:
            return self._dump({"error": "unsupported_format", "supported": ["txt", "md", "json", "docx"]})

        if target.exists() and not overwrite:
            return self._dump({"error": "target_exists", "path": str(target), "hint": "Set overwrite=true to replace."})

        target.parent.mkdir(parents=True, exist_ok=True)
        text = content or ""

        try:
            if fmt in {"txt", "md"}:
                target.write_text(text, encoding="utf-8")
            elif fmt == "json":
                try:
                    parsed = json.loads(text)
                    target.write_text(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                except Exception:
                    target.write_text(json.dumps({"content": text}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            elif fmt == "docx":
                ok, reason = self._write_docx(target, text)
                if not ok:
                    return self._dump(
                        {
                            "error": "docx_backend_unavailable",
                            "reason": reason,
                            "hint": "Install python-docx or export as txt/md/json.",
                        }
                    )
            else:
                return self._dump({"error": "unsupported_format", "supported": ["txt", "md", "json", "docx"]})
        except Exception as e:
            return self._dump({"error": "write_failed", "reason": str(e), "path": str(target)})

        try:
            size = target.stat().st_size
        except Exception:
            size = None
        return self._dump(
            {
                "ok": True,
                "format": fmt,
                "name": target.name,
                "path": str(target),
                "size": size,
                "dir": str(self._exports_dir),
            }
        )
