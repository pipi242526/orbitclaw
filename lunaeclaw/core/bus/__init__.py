"""Message bus module for decoupled channel-agent communication."""

from lunaeclaw.core.bus.events import InboundMessage, OutboundMessage
from lunaeclaw.core.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
