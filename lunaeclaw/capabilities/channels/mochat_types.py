"""Shared data types for Mochat channel modules."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class MochatBufferedEntry:
    """Buffered inbound entry for delayed dispatch."""

    raw_body: str
    author: str
    sender_name: str = ""
    sender_username: str = ""
    timestamp: int | None = None
    message_id: str = ""
    group_id: str = ""


@dataclass
class DelayState:
    """Per-target delayed message state."""

    entries: list[MochatBufferedEntry] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    timer: asyncio.Task | None = None


@dataclass
class MochatTarget:
    """Outbound target resolution result."""

    id: str
    is_panel: bool
