"""Message bus module for decoupled channel-agent communication."""

from orbitclaw.core.bus.events import InboundMessage, OutboundMessage
from orbitclaw.core.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
