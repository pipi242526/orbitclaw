"""Fallback worker task management helpers for Mochat channel."""

from __future__ import annotations

import asyncio
from collections.abc import Callable


def ensure_fallback_tasks(
    session_ids: set[str],
    panel_ids: set[str],
    session_tasks: dict[str, asyncio.Task],
    panel_tasks: dict[str, asyncio.Task],
    create_session_task: Callable[[str], asyncio.Task],
    create_panel_task: Callable[[str], asyncio.Task],
) -> None:
    """Ensure fallback workers exist for all known sessions/panels."""
    for session_id in sorted(session_ids):
        task = session_tasks.get(session_id)
        if not task or task.done():
            session_tasks[session_id] = create_session_task(session_id)
    for panel_id in sorted(panel_ids):
        task = panel_tasks.get(panel_id)
        if not task or task.done():
            panel_tasks[panel_id] = create_panel_task(panel_id)


async def stop_fallback_tasks(
    session_tasks: dict[str, asyncio.Task],
    panel_tasks: dict[str, asyncio.Task],
) -> None:
    """Cancel all fallback tasks and clear maps."""
    tasks = [*session_tasks.values(), *panel_tasks.values()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    session_tasks.clear()
    panel_tasks.clear()
