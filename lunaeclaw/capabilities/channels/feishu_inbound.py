"""Inbound content parsing helpers for Feishu channel."""

from __future__ import annotations

import json

from lunaeclaw.capabilities.channels.feishu_parser import (
    extract_post_text,
    extract_share_card_content,
)

MSG_TYPE_MAP = {
    "image": "[image]",
    "audio": "[audio]",
    "file": "[file]",
    "sticker": "[sticker]",
}

SHARE_LIKE_TYPES = {
    "share_chat",
    "share_user",
    "interactive",
    "share_calendar_event",
    "system",
    "merge_forward",
}


def safe_parse_content_json(raw_content: str | None) -> dict:
    """Parse message content JSON with tolerant fallback."""
    if not raw_content:
        return {}
    try:
        parsed = json.loads(raw_content)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_non_media_content(msg_type: str, content_json: dict) -> list[str] | None:
    """Parse non-media message types; return None for media types."""
    if msg_type in {"image", "audio", "file", "media"}:
        return None

    if msg_type == "text":
        text = content_json.get("text", "")
        return [text] if isinstance(text, str) and text else []

    if msg_type == "post":
        text = extract_post_text(content_json)
        return [text] if text else []

    if msg_type in SHARE_LIKE_TYPES:
        text = extract_share_card_content(content_json, msg_type)
        return [text] if text else []

    return [MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]")]
