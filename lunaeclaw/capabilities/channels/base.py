"""Base channel interface for chat platforms."""

import re
from abc import ABC, abstractmethod
from typing import Any

from loguru import logger

from lunaeclaw.core.bus.events import InboundMessage, OutboundMessage
from lunaeclaw.core.bus.queue import MessageBus


class BaseChannel(ABC):
    """
    Abstract base class for chat channel implementations.

    Each channel (Telegram, Discord, etc.) should implement this interface
    to integrate with the lunaeclaw message bus.
    """

    name: str = "base"
    _ENV_PLACEHOLDER_RE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")
    _INVISIBLE_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff")

    def __init__(self, config: Any, bus: MessageBus):
        """
        Initialize the channel.

        Args:
            config: Channel-specific configuration.
            bus: The message bus for communication.
        """
        self.config = config
        self.bus = bus
        self._running = False

    @abstractmethod
    async def start(self) -> None:
        """
        Start the channel and begin listening for messages.

        This should be a long-running async task that:
        1. Connects to the chat platform
        2. Listens for incoming messages
        3. Forwards messages to the bus via _handle_message()
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel and clean up resources."""
        pass

    @abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """
        Send a message through this channel.

        Args:
            msg: The message to send.
        """
        pass

    def _prepare_credential(self, field_name: str, value: Any, *, required: bool = True) -> str | None:
        """
        Normalize credential-like config values and detect unresolved placeholders.

        - strips leading/trailing whitespace
        - removes common invisible copy/paste chars (ZWSP/BOM)
        - blocks unresolved ${ENV_VAR} placeholders
        """
        raw = "" if value is None else str(value)
        normalized = raw
        for ch in self._INVISIBLE_CHARS:
            normalized = normalized.replace(ch, "")
        normalized = normalized.strip()

        if normalized != raw:
            logger.warning(
                "Channel {} credential `{}` contains hidden/whitespace characters; sanitized before use",
                self.name,
                field_name,
            )

        if not normalized:
            if required:
                logger.error("Channel {} credential `{}` not configured", self.name, field_name)
            return None

        if self._ENV_PLACEHOLDER_RE.match(normalized):
            logger.error(
                "Channel {} credential `{}` is unresolved env placeholder: {}",
                self.name,
                field_name,
                normalized,
            )
            return None

        return normalized

    def is_allowed(self, sender_id: str) -> bool:
        """
        Check if a sender is allowed to use this bot.

        Args:
            sender_id: The sender's identifier.

        Returns:
            True if allowed, False otherwise.
        """
        allow_list = getattr(self.config, "allow_from", [])
        if (
            allow_list
            and all(self._ENV_PLACEHOLDER_RE.match(str(item).strip()) for item in allow_list)
        ):
            if not getattr(self, "_warned_unresolved_allow_from", False):
                logger.warning(
                    "Channel {} allow_from contains unresolved env placeholders: {}",
                    self.name,
                    allow_list,
                )
                self._warned_unresolved_allow_from = True

        # If no allow list, allow everyone
        if not allow_list:
            return True

        normalized_allow: set[str] = set()
        normalized_allow_ci: set[str] = set()
        for item in allow_list:
            text = str(item or "").strip()
            if not text:
                continue
            normalized_allow.add(text)
            normalized_allow_ci.add(text.lower())
            if text.startswith("@") and len(text) > 1:
                normalized_allow.add(text[1:])
                normalized_allow_ci.add(text[1:].lower())

        if not normalized_allow:
            return True

        sender_str = str(sender_id or "").strip()
        sender_parts = [p.strip() for p in sender_str.split("|") if p and p.strip()]
        sender_parts.append(sender_str)
        sender_variants: set[str] = set()
        sender_variants_ci: set[str] = set()
        for part in sender_parts:
            sender_variants.add(part)
            sender_variants_ci.add(part.lower())
            if not part.startswith("@"):
                sender_variants.add(f"@{part}")
                sender_variants_ci.add(f"@{part}".lower())

        if sender_variants & normalized_allow:
            return True
        if sender_variants_ci & normalized_allow_ci:
            return True
        return False

    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """
        Handle an incoming message from the chat platform.

        This method checks permissions and forwards to the bus.

        Args:
            sender_id: The sender's identifier.
            chat_id: The chat/channel identifier.
            content: Message text content.
            media: Optional list of media URLs.
            attachments: Optional structured attachment objects.
            metadata: Optional channel-specific metadata.
        """
        if not self.is_allowed(sender_id):
            logger.warning(
                "Access denied for sender {} on channel {}. "
                "Add them to allowFrom list in config to grant access.",
                sender_id, self.name,
            )
            return

        media_paths = list(media or [])
        structured_attachments = list(attachments or [])
        if media_paths and not structured_attachments:
            # Backward-compatible fallback: derive attachment objects from media paths.
            structured_attachments = [{"path": path} for path in media_paths if isinstance(path, str) and path]

        msg = InboundMessage(
            channel=self.name,
            sender_id=str(sender_id),
            chat_id=str(chat_id),
            content=content,
            media=media_paths,
            attachments=structured_attachments,
            metadata=metadata or {}
        )

        await self.bus.publish_inbound(msg)

    @property
    def is_running(self) -> bool:
        """Check if the channel is running."""
        return self._running
