"""Notify payload conversion helpers for Mochat channel."""

from __future__ import annotations

from typing import Any

from orbitclaw.capabilities.channels.mochat_helpers import make_synthetic_event, str_field


def build_panel_notify_event(payload: Any, *, panel_set: set[str]) -> tuple[str, dict[str, Any]] | None:
    """Convert notify:chat.message.* payload into panel inbound event."""
    if not isinstance(payload, dict):
        return None
    group_id = str_field(payload, "groupId")
    panel_id = str_field(payload, "converseId", "panelId")
    if not group_id or not panel_id:
        return None
    if panel_set and panel_id not in panel_set:
        return None

    event = make_synthetic_event(
        message_id=str(payload.get("_id") or payload.get("messageId") or ""),
        author=str(payload.get("author") or ""),
        content=payload.get("content"),
        meta=payload.get("meta"),
        group_id=group_id,
        converse_id=panel_id,
        timestamp=payload.get("createdAt"),
        author_info=payload.get("authorInfo"),
    )
    return panel_id, event


def build_session_notify_event(payload: Any, *, session_id: str) -> dict[str, Any] | None:
    """Convert notify:chat.inbox.append payload into session inbound event."""
    if not isinstance(payload, dict) or payload.get("type") != "message":
        return None
    detail = payload.get("payload")
    if not isinstance(detail, dict):
        return None
    if str_field(detail, "groupId"):
        return None

    return make_synthetic_event(
        message_id=str(detail.get("messageId") or payload.get("_id") or ""),
        author=str(detail.get("messageAuthor") or ""),
        content=str(detail.get("messagePlainContent") or detail.get("messageSnippet") or ""),
        meta={"source": "notify:chat.inbox.append", "converseId": str_field(detail, "converseId")},
        group_id="",
        converse_id=str_field(detail, "converseId"),
        timestamp=payload.get("createdAt"),
    )
