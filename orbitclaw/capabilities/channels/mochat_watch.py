"""Watch-payload parsing helpers for Mochat channel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orbitclaw.capabilities.channels.mochat_helpers import str_field


@dataclass
class ParsedWatchPayload:
    target_id: str
    cursor: int | None
    events: list[dict[str, Any]]


def parse_mochat_watch_payload(payload: dict[str, Any]) -> ParsedWatchPayload | None:
    """Parse raw watch payload into normalized structure."""
    if not isinstance(payload, dict):
        return None
    target_id = str_field(payload, "sessionId")
    if not target_id:
        return None
    events = payload.get("events")
    if not isinstance(events, list):
        return ParsedWatchPayload(target_id=target_id, cursor=None, events=[])
    normalized = [event for event in events if isinstance(event, dict)]
    cursor = payload.get("cursor")
    return ParsedWatchPayload(target_id=target_id, cursor=cursor if isinstance(cursor, int) else None, events=normalized)


def iter_mochat_message_add_events(events: list[dict[str, Any]]) -> list[tuple[int | None, dict[str, Any]]]:
    """Return message.add events along with optional sequence number."""
    out: list[tuple[int | None, dict[str, Any]]] = []
    for event in events:
        if event.get("type") != "message.add":
            continue
        seq = event.get("seq")
        out.append((seq if isinstance(seq, int) else None, event))
    return out
