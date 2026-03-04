"""State persistence helpers for Mochat channel."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def load_mochat_session_cursors(cursor_path: Path) -> dict[str, int]:
    """Load persisted session cursors from disk."""
    if not cursor_path.exists():
        return {}
    data = json.loads(cursor_path.read_text("utf-8"))
    cursors = data.get("cursors") if isinstance(data, dict) else None
    if not isinstance(cursors, dict):
        return {}
    parsed: dict[str, int] = {}
    for session_id, cursor in cursors.items():
        if isinstance(session_id, str) and isinstance(cursor, int) and cursor >= 0:
            parsed[session_id] = cursor
    return parsed


def save_mochat_session_cursors(state_dir: Path, cursor_path: Path, cursors: dict[str, int]) -> None:
    """Persist session cursors to disk."""
    state_dir.mkdir(parents=True, exist_ok=True)
    cursor_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "cursors": cursors,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "utf-8",
    )
