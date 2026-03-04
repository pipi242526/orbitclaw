"""Outbound routing helpers for Feishu channel."""

from __future__ import annotations

import os


def resolve_receive_id_type(chat_id: str) -> str:
    """Resolve Feishu receive_id_type from OrbitClaw chat_id."""
    return "chat_id" if str(chat_id).startswith("oc_") else "open_id"


def classify_media_ext(file_path: str, *, image_exts: set[str], audio_exts: set[str]) -> tuple[bool, str, str]:
    """Classify outbound media file by extension.

    Returns: (is_image, msg_type, ext)
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext in image_exts:
        return True, "image", ext
    media_type = "audio" if ext in audio_exts else "file"
    return False, media_type, ext
