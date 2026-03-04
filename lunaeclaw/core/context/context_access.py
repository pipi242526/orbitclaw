"""Context/session access helpers for turn handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lunaeclaw.core.agent.turn_planner import collect_media_paths
from lunaeclaw.services.session.manager import Session

if TYPE_CHECKING:
    from lunaeclaw.core.bus.events import InboundMessage
    from lunaeclaw.services.session.manager import Session


def get_or_create_session(loop: Any, *, session_key: str) -> "Session":
    """Get existing session or create one."""
    return loop.sessions.get_or_create(session_key)


def get_effective_model(loop: Any, *, session: "Session") -> str:
    """Resolve effective model for a session (override or default)."""
    return loop._effective_model_for_session(session)


def sync_subagent_model(loop: Any, *, model: str) -> None:
    """Keep subagent manager model aligned with active session model."""
    loop.subagents.model = model


def build_initial_messages(
    loop: Any,
    *,
    session: "Session",
    msg: "InboundMessage",
) -> list[dict]:
    """Build provider input messages for one turn."""
    return loop.context.build_messages(
        history=session.get_history(max_messages=loop.memory_window),
        current_message=msg.content,
        media=collect_media_paths(msg) or None,
        channel=msg.channel,
        chat_id=msg.chat_id,
    )


def build_system_messages(
    loop: Any,
    *,
    session: "Session",
    current_message: str,
    channel: str,
    chat_id: str,
) -> list[dict]:
    """Build provider input messages for system-originated turn."""
    return loop.context.build_messages(
        history=session.get_history(max_messages=loop.memory_window),
        current_message=current_message,
        channel=channel,
        chat_id=chat_id,
    )


def persist_turn(
    loop: Any,
    *,
    session: "Session",
    user_message: str,
    final_content: str,
    tools_used: list[str] | None = None,
) -> None:
    """Persist completed user/assistant turn to session storage."""
    session.add_message("user", user_message)
    session.add_message(
        "assistant",
        final_content,
        tools_used=tools_used if tools_used else None,
    )
    loop.sessions.save(session)


def save_session(loop: Any, *, session: "Session") -> None:
    """Persist session metadata/content changes."""
    loop.sessions.save(session)


def invalidate_session(loop: Any, *, session_key: str) -> None:
    """Invalidate cached session so next access starts fresh."""
    loop.sessions.invalidate(session_key)


def new_temp_session(*, session_key: str) -> "Session":
    """Create temporary session object for consolidation/archive operations."""
    return Session(key=session_key)
