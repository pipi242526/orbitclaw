"""Subscription ACK parsing helpers for Mochat channel."""

from __future__ import annotations

from typing import Any


def parse_subscribe_sessions_ack(ack: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize subscribeSessions ACK data into payload items."""
    data = ack.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        sessions = data.get("sessions")
        if isinstance(sessions, list):
            return [item for item in sessions if isinstance(item, dict)]
        if "sessionId" in data:
            return [data]
    return []
