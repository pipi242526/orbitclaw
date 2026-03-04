"""Refresh response parsing helpers for Mochat channel."""

from __future__ import annotations

from typing import Any

from lunaeclaw.capabilities.channels.mochat_helpers import str_field


def parse_mochat_sessions(response: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    """Parse session list response into session ids and converse map."""
    sessions = response.get("sessions")
    if not isinstance(sessions, list):
        return [], {}

    session_ids: list[str] = []
    converse_map: dict[str, str] = {}
    for item in sessions:
        if not isinstance(item, dict):
            continue
        session_id = str_field(item, "sessionId")
        if not session_id:
            continue
        session_ids.append(session_id)
        converse_id = str_field(item, "converseId")
        if converse_id:
            converse_map[converse_id] = session_id
    return session_ids, converse_map


def parse_mochat_panels(response: dict[str, Any]) -> list[str]:
    """Parse panel list response into valid panel ids."""
    raw_panels = response.get("panels")
    if not isinstance(raw_panels, list):
        return []

    panel_ids: list[str] = []
    for item in raw_panels:
        if not isinstance(item, dict):
            continue
        panel_type = item.get("type")
        if isinstance(panel_type, int) and panel_type != 0:
            continue
        panel_id = str_field(item, "id", "_id")
        if panel_id:
            panel_ids.append(panel_id)
    return panel_ids
