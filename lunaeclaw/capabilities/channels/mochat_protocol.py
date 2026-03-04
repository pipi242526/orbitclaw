"""Protocol parsing helpers for Mochat inbound events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lunaeclaw.capabilities.channels.mochat_helpers import (
    make_synthetic_event,
    normalize_content,
    parse_timestamp,
    resolve_was_mentioned,
    safe_dict,
    str_field,
)
from lunaeclaw.capabilities.channels.mochat_mapper import resolve_require_mention
from lunaeclaw.capabilities.channels.mochat_types import MochatBufferedEntry
from lunaeclaw.platform.config.schema import MochatConfig


@dataclass
class ParsedMochatInbound:
    """Parsed Mochat inbound event and routing flags."""

    author: str
    message_id: str
    entry: MochatBufferedEntry
    was_mentioned: bool
    use_delay: bool
    should_skip: bool


def parse_mochat_inbound_event(
    event: dict[str, Any],
    *,
    config: MochatConfig,
    target_id: str,
    target_kind: str,
) -> ParsedMochatInbound | None:
    """Parse one Mochat event into normalized inbound data."""
    payload = event.get("payload")
    if not isinstance(payload, dict):
        return None

    author = str_field(payload, "author")
    message_id = str_field(payload, "messageId")

    raw_body = normalize_content(payload.get("content")) or "[empty message]"
    ai = safe_dict(payload.get("authorInfo"))
    sender_name = str_field(ai, "nickname", "email")
    sender_username = str_field(ai, "agentId")

    group_id = str_field(payload, "groupId")
    is_group = bool(group_id)
    was_mentioned = resolve_was_mentioned(payload, config.agent_user_id)
    require_mention = target_kind == "panel" and is_group and resolve_require_mention(config, target_id, group_id)
    use_delay = target_kind == "panel" and config.reply_delay_mode == "non-mention"

    entry = MochatBufferedEntry(
        raw_body=raw_body,
        author=author,
        sender_name=sender_name,
        sender_username=sender_username,
        timestamp=parse_timestamp(event.get("timestamp")),
        message_id=message_id,
        group_id=group_id,
    )
    return ParsedMochatInbound(
        author=author,
        message_id=message_id,
        entry=entry,
        was_mentioned=was_mentioned,
        use_delay=use_delay,
        should_skip=require_mention and not was_mentioned and not use_delay,
    )


def parse_panel_poll_events(response: dict[str, Any], *, panel_id: str) -> list[dict[str, Any]]:
    """Parse panel polling response into synthetic inbound events."""
    messages = response.get("messages")
    if not isinstance(messages, list):
        return []
    group_id = str(response.get("groupId") or "")

    events: list[dict[str, Any]] = []
    for item in reversed(messages):
        if not isinstance(item, dict):
            continue
        events.append(
            make_synthetic_event(
                message_id=str(item.get("messageId") or ""),
                author=str(item.get("author") or ""),
                content=item.get("content"),
                meta=item.get("meta"),
                group_id=group_id,
                converse_id=panel_id,
                timestamp=item.get("createdAt"),
                author_info=item.get("authorInfo"),
            )
        )
    return events
