"""POST action handlers for Web UI pages.

This module intentionally keeps only thin delegating wrappers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lunaeclaw.app.webui.actions_channels import handle_post_channels as _handle_post_channels
from lunaeclaw.app.webui.actions_chat import handle_post_chat as _handle_post_chat
from lunaeclaw.app.webui.actions_endpoints import handle_post_endpoints as _handle_post_endpoints
from lunaeclaw.app.webui.actions_mcp import handle_post_mcp as _handle_post_mcp
from lunaeclaw.app.webui.actions_media import handle_post_media as _handle_post_media
from lunaeclaw.app.webui.actions_skills import handle_post_skills as _handle_post_skills


def handle_post_chat(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /chat POST actions."""
    _handle_post_chat(handler, form)


def handle_post_endpoints(handler: Any, form: dict[str, list[str]], *, cfg_path: Path) -> None:
    """Handle /endpoints POST actions."""
    _handle_post_endpoints(handler, form, cfg_path=cfg_path)


def handle_post_channels(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /channels POST actions."""
    _handle_post_channels(handler, form)


def handle_post_mcp(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /mcp POST actions."""
    _handle_post_mcp(handler, form)


def handle_post_skills(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /skills POST actions."""
    _handle_post_skills(handler, form)


def handle_post_media(handler: Any, form: dict[str, list[str]]) -> None:
    """Handle /media POST actions."""
    _handle_post_media(handler, form)
