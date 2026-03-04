"""Async message queue for decoupled channel-agent communication."""

import asyncio
from typing import Literal

from loguru import logger

from lunaeclaw.core.bus.events import InboundMessage, OutboundMessage


class MessageBus:
    """
    Async message bus that decouples chat channels from the agent core.

    Channels push messages to the inbound queue, and the agent processes
    them and pushes responses to the outbound queue.
    """

    def __init__(
        self,
        *,
        inbound_maxsize: int = 0,
        outbound_maxsize: int = 0,
        drop_progress_outbound_when_full: bool = True,
        inbound_overflow_policy: Literal["block", "drop_oldest", "drop_newest"] = "drop_oldest",
        outbound_full_wait_seconds: float = 1.0,
    ):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue(maxsize=max(0, int(inbound_maxsize or 0)))
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue(maxsize=max(0, int(outbound_maxsize or 0)))
        self._drop_progress_outbound_when_full = bool(drop_progress_outbound_when_full)
        self._inbound_overflow_policy = self._normalize_policy(inbound_overflow_policy)
        self._outbound_full_wait_seconds = max(0.0, float(outbound_full_wait_seconds or 0.0))
        self.inbound_dropped = 0
        self.outbound_dropped = 0

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent."""
        if not self.inbound.full():
            self.inbound.put_nowait(msg)
            return
        if self._inbound_overflow_policy == "block":
            await self.inbound.put(msg)
            return
        if self._inbound_overflow_policy == "drop_newest":
            self.inbound_dropped += 1
            logger.warning("Dropping inbound message because inbound queue is full (policy=drop_newest)")
            return
        dropped = self._drop_oldest_nowait(self.inbound)
        if dropped:
            self.inbound_dropped += 1
            logger.warning("Dropped oldest inbound message because inbound queue is full (policy=drop_oldest)")
        try:
            self.inbound.put_nowait(msg)
        except asyncio.QueueFull:
            self.inbound_dropped += 1
            logger.warning("Dropping inbound message because inbound queue is still full after eviction")

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        if self.outbound.full() and self._drop_progress_outbound_when_full and self._is_progress_outbound(msg):
            self.outbound_dropped += 1
            logger.warning("Dropping progress outbound message because outbound queue is full")
            return
        if not self.outbound.full():
            self.outbound.put_nowait(msg)
            return
        try:
            await asyncio.wait_for(self.outbound.put(msg), timeout=self._outbound_full_wait_seconds)
            return
        except TimeoutError:
            pass
        dropped = self._drop_oldest_nowait(self.outbound)
        if dropped:
            self.outbound_dropped += 1
            logger.warning("Dropped oldest outbound message because outbound queue remained full")
        try:
            self.outbound.put_nowait(msg)
        except asyncio.QueueFull:
            self.outbound_dropped += 1
            logger.warning("Dropping outbound message because outbound queue is still full after eviction")

    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()

    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()

    @staticmethod
    def _is_progress_outbound(msg: OutboundMessage) -> bool:
        metadata = msg.metadata if isinstance(msg.metadata, dict) else {}
        return bool(metadata.get("_progress"))

    @staticmethod
    def _normalize_policy(policy: str) -> Literal["block", "drop_oldest", "drop_newest"]:
        val = str(policy or "").strip().lower().replace("-", "_")
        if val in {"block", "drop_oldest", "drop_newest"}:
            return val  # type: ignore[return-value]
        return "drop_oldest"

    @staticmethod
    def _drop_oldest_nowait(queue: asyncio.Queue) -> bool:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            return False
        # We removed one item without processing it; mark done for queue accounting.
        queue.task_done()
        return True
