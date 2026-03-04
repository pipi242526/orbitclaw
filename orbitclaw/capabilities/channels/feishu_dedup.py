"""Dedup cache helpers for Feishu channel."""

from __future__ import annotations

from collections import OrderedDict


def remember_feishu_message_id(cache: OrderedDict[str, None], message_id: str, *, max_entries: int = 1000) -> bool:
    """Return True when message id is already seen; otherwise remember it."""
    if message_id in cache:
        return True
    cache[message_id] = None
    while len(cache) > max_entries:
        cache.popitem(last=False)
    return False
