"""Message tool for sending messages to users."""

from typing import Any, Awaitable, Callable

from lunaeclaw.capabilities.tools.base import Tool
from lunaeclaw.core.bus.events import OutboundMessage


class MessageTool(Tool):
    """Tool to send messages to users on chat channels."""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        output_sanitizer: Callable[[str], str] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
        default_message_id: str | None = None,
    ):
        self._send_callback = send_callback
        self._output_sanitizer = output_sanitizer
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id
        self._default_message_id = default_message_id
        self._sent_in_turn: bool = False

    def set_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Set the current message context."""
        self._default_channel = channel
        self._default_chat_id = chat_id
        self._default_message_id = message_id

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        self._send_callback = callback

    def set_output_sanitizer(self, sanitizer: Callable[[str], str]) -> None:
        """Set optional sanitizer for user-visible message content."""
        self._output_sanitizer = sanitizer

    def start_turn(self) -> None:
        """Reset per-turn send tracking."""
        self._sent_in_turn = False

    @property
    def name(self) -> str:
        return "message"

    @property
    def description(self) -> str:
        return "Send a message to the user. Use this when you want to communicate something."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The message content to send"
                },
                "channel": {
                    "type": "string",
                    "description": "Optional: target channel (telegram, discord, etc.)"
                },
                "chat_id": {
                    "type": "string",
                    "description": "Optional: target chat/user ID"
                },
                "reply_to": {
                    "type": "string",
                    "description": "Optional: reply target message id/thread id (channel-specific)"
                },
                "media": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional: list of file paths to attach (images, audio, documents)"
                },
                "attachments": {
                    "type": "array",
                    "description": "Optional: structured attachments (e.g. [{\"path\":\"/tmp/a.pdf\",\"name\":\"a.pdf\"}])",
                    "items": {"type": "object"}
                },
                "actions": {
                    "type": "array",
                    "description": "Optional interactive actions, e.g. [{\"id\":\"opt_a\",\"title\":\"Option A\"}]",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "value": {"type": "string"},
                            "prompt": {"type": "string"},
                        },
                    },
                }
            },
            "required": ["content"]
        }

    async def execute(
        self,
        content: str,
        channel: str | None = None,
        chat_id: str | None = None,
        message_id: str | None = None,
        reply_to: str | None = None,
        media: list[str] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        actions: list[dict[str, Any]] | None = None,
        **kwargs: Any
    ) -> str:
        channel = channel or self._default_channel
        chat_id = chat_id or self._default_chat_id
        resolved_reply_to = reply_to or message_id or self._default_message_id

        if not channel or not chat_id:
            return "Error: No target channel/chat specified"

        if not self._send_callback:
            return "Error: Message sending not configured"

        normalized_attachments = list(attachments or [])
        normalized_media = list(media or [])
        outbound_content = str(content or "")
        if self._output_sanitizer is not None:
            outbound_content = self._output_sanitizer(outbound_content)
        for item in normalized_attachments:
            if isinstance(item, dict):
                path = item.get("path")
                if isinstance(path, str) and path and path not in normalized_media:
                    normalized_media.append(path)

        msg = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=outbound_content,
            reply_to=str(resolved_reply_to) if resolved_reply_to else None,
            media=normalized_media,
            attachments=normalized_attachments,
            actions=list(actions or []),
            metadata={
                "message_id": resolved_reply_to,
            }
        )

        try:
            await self._send_callback(msg)
            self._sent_in_turn = True
            media_info = f" with {len(normalized_media)} attachments" if normalized_media else ""
            return f"Message sent to {channel}:{chat_id}{media_info}"
        except Exception as e:
            return f"Error sending message: {str(e)}"
