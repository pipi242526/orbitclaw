"""Chat channels module with plugin architecture."""

from orbitclaw.capabilities.channels.base import BaseChannel
from orbitclaw.capabilities.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
