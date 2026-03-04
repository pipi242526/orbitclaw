"""Turn planning helpers for AgentLoop message handling."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable

from orbitclaw.core.bus.events import OutboundMessage

if TYPE_CHECKING:
    from orbitclaw.core.bus.events import InboundMessage
    from orbitclaw.core.bus.queue import MessageBus


def resolve_reply_to(metadata: dict[str, Any] | None) -> str | None:
    """Resolve reply target from channel metadata."""
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("reply_to") or metadata.get("message_id")
    return str(value) if value is not None and str(value).strip() else None


def collect_media_paths(msg: "InboundMessage") -> list[str]:
    """Collect attachment file paths while preserving legacy media support."""
    paths: list[str] = []
    for path in (msg.media or []):
        if isinstance(path, str) and path:
            paths.append(path)
    for item in (msg.attachments or []):
        if isinstance(item, dict):
            path = item.get("path")
            if isinstance(path, str) and path and path not in paths:
                paths.append(path)
    return paths


def make_outbound(
    *,
    msg: "InboundMessage",
    content: str,
    reply_to_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> OutboundMessage:
    """Build a channel response using original inbound message metadata."""
    return OutboundMessage(
        channel=msg.channel,
        chat_id=msg.chat_id,
        content=content,
        reply_to=reply_to_id,
        metadata=metadata if metadata is not None else (msg.metadata or {}),
    )


def build_cli_progress_callback(
    *,
    bus: "MessageBus",
    msg: "InboundMessage",
    reply_to_id: str | None,
) -> Callable[[str], Awaitable[None]]:
    """Build progress callback for CLI channel only."""

    async def _publish(content: str) -> None:
        if msg.channel != "cli":
            return
        meta = dict(msg.metadata or {})
        meta["_progress"] = True
        await bus.publish_outbound(
            OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=content,
                reply_to=reply_to_id,
                metadata=meta,
            )
        )

    return _publish


def build_processing_notice_sender(
    *,
    bus: "MessageBus",
    msg: "InboundMessage",
    reply_to_id: str | None,
    notice_text: str,
) -> Callable[[], Awaitable[None]]:
    """Build delayed processing notice publisher for non-CLI channels."""

    async def _send_notice() -> None:
        meta = dict(msg.metadata or {})
        meta["_progress"] = True
        meta["_progress_kind"] = "processing"
        await bus.publish_outbound(
            OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=notice_text,
                reply_to=reply_to_id,
                metadata=meta,
            )
        )

    return _send_notice

