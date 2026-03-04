"""Reusable Mochat parsing/normalization helpers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def safe_dict(value: Any) -> dict:
    """Return *value* if it's a dict, else empty dict."""
    return value if isinstance(value, dict) else {}


def str_field(src: dict, *keys: str) -> str:
    """Return first non-empty str value for keys."""
    for key in keys:
        val = src.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def make_synthetic_event(
    message_id: str,
    author: str,
    content: Any,
    meta: Any,
    group_id: str,
    converse_id: str,
    timestamp: Any = None,
    *,
    author_info: Any = None,
) -> dict[str, Any]:
    """Build a synthetic ``message.add`` event dict."""
    payload: dict[str, Any] = {
        "messageId": message_id,
        "author": author,
        "content": content,
        "meta": safe_dict(meta),
        "groupId": group_id,
        "converseId": converse_id,
    }
    if author_info is not None:
        payload["authorInfo"] = safe_dict(author_info)
    return {
        "type": "message.add",
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "payload": payload,
    }


def normalize_content(content: Any) -> str:
    """Normalize Mochat payload content to plain text."""
    if isinstance(content, str):
        return content.strip()
    if content is None:
        return ""
    try:
        return json.dumps(content, ensure_ascii=False)
    except TypeError:
        return str(content)


def extract_mention_ids(value: Any) -> list[str]:
    """Extract mention ids from heterogeneous payload structures."""
    if not isinstance(value, list):
        return []
    ids: list[str] = []
    for item in value:
        if isinstance(item, str):
            if item.strip():
                ids.append(item.strip())
        elif isinstance(item, dict):
            for key in ("id", "userId", "_id"):
                candidate = item.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    ids.append(candidate.strip())
                    break
    return ids


def resolve_was_mentioned(payload: dict[str, Any], agent_user_id: str) -> bool:
    """Resolve mention state from payload metadata and text fallback."""
    meta = payload.get("meta")
    if isinstance(meta, dict):
        if meta.get("mentioned") is True or meta.get("wasMentioned") is True:
            return True
        for field in ("mentions", "mentionIds", "mentionedUserIds", "mentionedUsers"):
            if agent_user_id and agent_user_id in extract_mention_ids(meta.get(field)):
                return True
    if not agent_user_id:
        return False
    content = payload.get("content")
    if not isinstance(content, str) or not content:
        return False
    return f"<@{agent_user_id}>" in content or f"@{agent_user_id}" in content


def parse_timestamp(value: Any) -> int | None:
    """Parse event timestamp to epoch milliseconds."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return None
