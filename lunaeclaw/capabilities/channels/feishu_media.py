"""Media decision helpers for Feishu channel."""

from __future__ import annotations

import os
from typing import Any


def resolve_upload_file_type(file_path: str, file_type_map: dict[str, str]) -> tuple[str, str, str]:
    """Resolve upload file type, name and extension from local path."""
    ext = os.path.splitext(file_path)[1].lower()
    file_type = file_type_map.get(ext, "stream")
    file_name = os.path.basename(file_path)
    return file_type, file_name, ext


def resolve_download_target(msg_type: str, content_json: dict[str, Any], message_id: str | None) -> tuple[str | None, str | None]:
    """Resolve download key and resource type for media message."""
    if not message_id:
        return None, None
    if msg_type == "image":
        key = content_json.get("image_key")
        return (str(key), "image") if key else (None, None)
    if msg_type in {"audio", "file", "media"}:
        key = content_json.get("file_key")
        return (str(key), msg_type) if key else (None, None)
    return None, None


def resolve_download_filename(msg_type: str, key: str, filename: str | None) -> str:
    """Resolve saved filename for downloaded media."""
    if filename:
        return filename
    if msg_type == "image":
        return f"{key[:16]}.jpg"
    ext = {"audio": ".opus", "media": ".mp4"}.get(msg_type, "")
    return f"{key[:16]}{ext}"


def format_media_content_text(msg_type: str, filename: str) -> str:
    """Build content text marker for downloaded media."""
    return f"[{msg_type}: {filename}]"


def format_media_download_failed_text(msg_type: str) -> str:
    """Build fallback content text marker when media download fails."""
    return f"[{msg_type}: download failed]"
