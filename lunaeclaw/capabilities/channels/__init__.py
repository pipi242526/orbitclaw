"""Chat channels module with plugin architecture."""

from lunaeclaw.capabilities.channels.base import BaseChannel
from lunaeclaw.capabilities.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
