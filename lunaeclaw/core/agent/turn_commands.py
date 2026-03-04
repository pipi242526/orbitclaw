"""Slash command helpers extracted from AgentLoop."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

from lunaeclaw.core.context.context_access import (
    get_effective_model,
    invalidate_session,
    new_temp_session,
    save_session,
)

if TYPE_CHECKING:
    from lunaeclaw.core.bus.events import InboundMessage, OutboundMessage
    from lunaeclaw.services.session.manager import Session


def register_builtin_commands(loop: Any) -> None:
    """Register built-in slash commands on AgentLoop."""
    loop.register_command(
        name="new",
        handler="_cmd_new",
        help_en="Start a new conversation",
        help_zh="开始新会话",
    )
    loop.register_command(
        name="model",
        handler="_cmd_model",
        help_en="Show or switch model for this session",
        help_zh="查看或切换当前会话模型",
    )
    loop.register_command(
        name="help",
        handler="_cmd_help",
        help_en="Show available commands",
        help_zh="查看可用命令",
        aliases=["h"],
    )


def parse_slash_command(text: str) -> tuple[str, str] | None:
    raw = (text or "").strip()
    if not raw.startswith("/") or raw == "/":
        return None
    body = raw[1:]
    name, _, arg = body.partition(" ")
    key = name.strip().lower()
    if not key:
        return None
    return key, arg.strip()


async def dispatch_command(
    loop: Any,
    *,
    command_name: str,
    command_arg: str,
    msg: "InboundMessage",
    session: "Session",
    mk_out: Callable[[str], "OutboundMessage"],
) -> "OutboundMessage | None":
    canonical = loop._command_aliases.get(command_name, command_name)
    spec = loop._command_specs.get(canonical)
    if not spec:
        return mk_out(loop.policy.unknown_command_text(command_name=command_name, user_message=msg.content))
    handler = getattr(loop, spec.handler)
    return await handler(command_arg=command_arg, msg=msg, session=session, mk_out=mk_out)


async def cmd_new(
    loop: Any,
    *,
    command_arg: str,
    msg: "InboundMessage",
    session: "Session",
    mk_out: Callable[[str], "OutboundMessage"],
) -> "OutboundMessage":
    _ = command_arg
    lock = loop._get_consolidation_lock(session.key)
    loop._consolidating.add(session.key)
    try:
        async with lock:
            snapshot = session.messages[session.last_consolidated:]
            if snapshot:
                temp = new_temp_session(session_key=session.key)
                temp.messages = list(snapshot)
                if not await loop._consolidate_memory(
                    temp,
                    archive_all=True,
                    model=get_effective_model(loop, session=session),
                ):
                    return mk_out(loop.policy.memory_archive_failed(user_message=msg.content))
    except Exception:
        logger.exception("/new archival failed for {}", session.key)
        return mk_out(loop.policy.memory_archive_failed(user_message=msg.content))
    finally:
        loop._consolidating.discard(session.key)
        loop._prune_consolidation_lock(session.key, lock)

    session.clear()
    save_session(loop, session=session)
    invalidate_session(loop, session_key=session.key)
    return mk_out(loop.policy.new_session_started(user_message=msg.content))


async def cmd_help(
    loop: Any,
    *,
    command_arg: str,
    msg: "InboundMessage",
    session: "Session",
    mk_out: Callable[[str], "OutboundMessage"],
) -> "OutboundMessage":
    _ = (command_arg, session)
    specs = sorted(loop._command_specs.values(), key=lambda s: s.name)
    lines = [(s.name, s.help_en, s.help_zh) for s in specs]
    return mk_out(loop.policy.help_text_from_specs(command_specs=lines, user_message=msg.content))


async def cmd_model(
    loop: Any,
    *,
    command_arg: str,
    msg: "InboundMessage",
    session: "Session",
    mk_out: Callable[[str], "OutboundMessage"],
) -> "OutboundMessage":
    arg = (command_arg or "").strip()
    current_model = get_effective_model(loop, session=session)
    if not arg:
        source = loop.policy.model_source_label(
            has_override=bool(session.metadata.get("model_override")),
            user_message=msg.content,
        )
        endpoint_lines = loop.policy.model_endpoints_hint_lines(
            endpoint_hints=loop.provider.list_switchable_endpoints(),
            user_message=msg.content,
        )
        return mk_out(
            loop.policy.model_status_text(
                current_model=current_model,
                default_model=loop.model,
                source=source,
                endpoint_lines=endpoint_lines,
                user_message=msg.content,
            )
        )
    if arg.lower() in {"reset", "default"}:
        session.metadata.pop("model_override", None)
        save_session(loop, session=session)
        return mk_out(loop.policy.model_reset_text(default_model=loop.model, user_message=msg.content))
    try:
        ok, detail = loop.provider.prepare_model(arg)
    except Exception as e:
        ok, detail = False, str(e)
    if not ok:
        return mk_out(loop.policy.model_switch_failed_text(detail=(detail or ""), user_message=msg.content))
    session.metadata["model_override"] = arg
    save_session(loop, session=session)
    return mk_out(
        loop.policy.model_switched_text(
            model_ref=arg,
            session_key=session.key,
            routing_detail=(detail or ""),
            user_message=msg.content,
        )
    )
