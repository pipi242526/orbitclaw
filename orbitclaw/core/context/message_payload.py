"""Message payload assembly helpers for ContextBuilder."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any


def estimate_message_chars(message: dict[str, Any]) -> int:
    """Estimate message size for history budget trimming."""
    content = message.get("content", "")
    size = 0
    if isinstance(content, str):
        size = len(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    size += len(item["text"])
                elif isinstance(item.get("image_url"), dict):
                    size += 128
                else:
                    size += 48
            else:
                size += len(str(item))
    else:
        size = len(str(content))
    return size + 48


def trim_history_by_chars(history: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """Trim history to fit in character budget, keeping the latest user turn boundary."""
    if limit <= 0:
        return history
    if not history:
        return history
    selected: list[dict[str, Any]] = []
    used = 0
    for msg in reversed(history):
        msg_size = estimate_message_chars(msg)
        if selected and (used + msg_size) > limit:
            break
        selected.append(msg)
        used += msg_size
        if used >= limit:
            break
    trimmed = list(reversed(selected))
    for idx, msg in enumerate(trimmed):
        if msg.get("role") == "user":
            return trimmed[idx:]
    return []


def append_runtime_context(
    user_content: str | list[dict[str, Any]],
    runtime_context: str,
) -> str | list[dict[str, Any]]:
    """Append runtime context at the tail user message for better prompt cache reuse."""
    runtime_block = f"[Runtime Context]\n{runtime_context}"
    if isinstance(user_content, str):
        return f"{user_content}\n\n{runtime_block}"
    content = list(user_content)
    content.append({"type": "text", "text": runtime_block})
    return content


def build_user_content(
    text: str,
    media: list[str] | None,
    *,
    max_inline_image_bytes: int,
) -> str | list[dict[str, Any]]:
    """Build user message content with optional base64-encoded images."""
    if not media:
        return text

    images = []
    non_image_attachments: list[str] = []
    oversized_images: list[str] = []
    for path in media:
        p = Path(path)
        mime, _ = mimetypes.guess_type(path)
        if not p.is_file():
            continue
        if not mime or not mime.startswith("image/"):
            non_image_attachments.append(str(p))
            continue
        file_size = p.stat().st_size
        if max_inline_image_bytes > 0 and file_size > max_inline_image_bytes:
            non_image_attachments.append(str(p))
            oversized_images.append(str(p))
            continue
        b64 = base64.b64encode(p.read_bytes()).decode()
        images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

    attachment_hint = ""
    if non_image_attachments or oversized_images:
        plain_text_exts = {".txt", ".md", ".log", ".json", ".yaml", ".yml", ".csv", ".tsv"}
        plain_text_files = [p for p in non_image_attachments if Path(p).suffix.lower() in plain_text_exts]
        binary_doc_files = [p for p in non_image_attachments if p not in plain_text_files]
        lines = "\n".join(f"- {p}" for p in non_image_attachments)
        hint_lines = []
        if plain_text_files:
            txt_lines = "\n".join(f"  - {p}" for p in plain_text_files)
            hint_lines.append(f"Plain-text files (prefer `read_file`):\n{txt_lines}")
        if binary_doc_files:
            doc_lines = "\n".join(f"  - {p}" for p in binary_doc_files)
            hint_lines.append(f"Document files (prefer `doc_read`):\n{doc_lines}")
        if oversized_images:
            large_img_lines = "\n".join(f"  - {p}" for p in oversized_images)
            hint_lines.append(
                "Large images skipped for inline vision to save tokens (prefer `image_read`):\n"
                f"{large_img_lines}"
            )
        attachment_hint = (
            "\n\nAttached local files (non-image):\n"
            f"{lines}\n"
            + ("\n" + "\n".join(hint_lines) if hint_lines else "")
        )

    if not images:
        return text + attachment_hint
    return images + [{"type": "text", "text": text + attachment_hint}]
