"""Dedup helpers for Mochat channel."""

from __future__ import annotations

from collections import deque


def remember_message_id(
    seen_set_map: dict[str, set[str]],
    seen_queue_map: dict[str, deque[str]],
    *,
    key: str,
    message_id: str,
    max_size: int,
) -> bool:
    """Track message id and return True when it's already seen."""
    seen_set = seen_set_map.setdefault(key, set())
    seen_queue = seen_queue_map.setdefault(key, deque())
    if message_id in seen_set:
        return True
    seen_set.add(message_id)
    seen_queue.append(message_id)
    while len(seen_queue) > max_size:
        seen_set.discard(seen_queue.popleft())
    return False
