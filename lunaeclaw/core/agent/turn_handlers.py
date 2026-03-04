"""Turn handlers extracted from AgentLoop for clearer orchestration flow."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Callable

from loguru import logger

from lunaeclaw.capabilities.tools.message import MessageTool
from lunaeclaw.core.agent.turn_planner import (
    build_cli_progress_callback,
    build_processing_notice_sender,
    make_outbound,
    resolve_reply_to,
)
from lunaeclaw.core.agent.turn_runner import cancel_task_safely, create_delayed_notice_task
from lunaeclaw.core.bus.events import InboundMessage, OutboundMessage
from lunaeclaw.core.context.context_access import (
    build_initial_messages,
    build_system_messages,
    get_effective_model,
    get_or_create_session,
    persist_turn,
    sync_subagent_model,
)

if TYPE_CHECKING:
    from lunaeclaw.services.session.manager import Session


async def process_system_message(loop: Any, msg: "InboundMessage") -> OutboundMessage:
    """Process system-originated message routed through synthetic channel/chat."""
    channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id else ("cli", msg.chat_id))
    logger.info("Processing system message from {}", msg.sender_id)
    key = f"{channel}:{chat_id}"
    session = get_or_create_session(loop, session_key=key)
    loop._set_tool_context(channel, chat_id, resolve_reply_to(msg.metadata))
    messages = build_system_messages(
        loop,
        session=session,
        current_message=msg.content,
        channel=channel,
        chat_id=chat_id,
    )
    final_content, _ = await loop._run_agent_loop(messages, user_message=msg.content)
    if final_content is None:
        final_content = loop.policy.background_task_completed(user_message=msg.content)
    final_content = await loop._enforce_reply_language(
        user_message=msg.content,
        draft_reply=final_content,
        model=get_effective_model(loop, session=session),
    )
    persist_turn(
        loop,
        session=session,
        user_message=f"[System: {msg.sender_id}] {msg.content}",
        final_content=final_content,
    )
    return OutboundMessage(channel=channel, chat_id=chat_id, content=final_content)


async def try_handle_slash_command(
    loop: Any,
    *,
    msg: "InboundMessage",
    session: "Session",
    mk_out: Callable[[str], OutboundMessage],
) -> OutboundMessage | None:
    """Parse and dispatch slash command if present."""
    parsed_cmd = loop._parse_slash_command(msg.content)
    if not parsed_cmd:
        return None
    command_name, command_arg = parsed_cmd
    return await loop._dispatch_command(
        command_name=command_name,
        command_arg=command_arg,
        msg=msg,
        session=session,
        mk_out=mk_out,
    )


def maybe_schedule_consolidation(loop: Any, session: "Session") -> None:
    """Schedule background memory consolidation when threshold is exceeded."""
    unconsolidated = len(session.messages) - session.last_consolidated
    if unconsolidated < loop.memory_window or session.key in loop._consolidating:
        return
    loop._consolidating.add(session.key)
    lock = loop._get_consolidation_lock(session.key)

    async def _consolidate_and_unlock() -> None:
        try:
            async with lock:
                await loop._consolidate_memory(
                    session,
                    model=get_effective_model(loop, session=session),
                )
        finally:
            loop._consolidating.discard(session.key)
            loop._prune_consolidation_lock(session.key, lock)
            _task = asyncio.current_task()
            if _task is not None:
                loop._consolidation_tasks.discard(_task)

    task = asyncio.create_task(_consolidate_and_unlock())
    loop._consolidation_tasks.add(task)


async def execute_regular_message_turn(
    loop: Any,
    *,
    msg: "InboundMessage",
    session: "Session",
    reply_to_id: str | None,
    on_progress: Callable[[str], Any] | None,
    mk_out: Callable[[str], OutboundMessage],
) -> OutboundMessage | None:
    """Execute normal user turn and return final outbound message (or None when tool already sent)."""
    loop._set_tool_context(msg.channel, msg.chat_id, reply_to_id)
    if message_tool := loop.tools.get("message"):
        if isinstance(message_tool, MessageTool):
            message_tool.start_turn()

    initial_messages = build_initial_messages(loop, session=session, msg=msg)
    effective_model = get_effective_model(loop, session=session)
    sync_subagent_model(loop, model=effective_model)

    bus_progress = build_cli_progress_callback(
        bus=loop.bus,
        msg=msg,
        reply_to_id=reply_to_id,
    )

    processing_notice_task: asyncio.Task | None = None
    if on_progress is None and msg.channel != "cli":
        send_processing_notice = build_processing_notice_sender(
            bus=loop.bus,
            msg=msg,
            reply_to_id=reply_to_id,
            notice_text=loop._processing_notice_text(msg.content),
        )
        processing_notice_task = create_delayed_notice_task(
            delay_seconds=loop._processing_notice_delay_for_channel(msg.channel),
            send_notice=send_processing_notice,
        )

    try:
        final_content, tools_used = await loop._run_agent_loop(
            initial_messages,
            on_progress=on_progress or bus_progress,
            model=effective_model,
            emit_tool_hints=(msg.channel == "cli"),
            user_message=msg.content,
        )
    finally:
        await cancel_task_safely(processing_notice_task)

    if final_content is None:
        final_content = loop.policy.no_response_fallback(user_message=msg.content)
    final_content = await loop._enforce_reply_language(
        user_message=msg.content,
        draft_reply=final_content,
        model=effective_model,
    )

    preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
    logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)

    persist_turn(
        loop,
        session=session,
        user_message=msg.content,
        final_content=final_content,
        tools_used=tools_used,
    )

    if message_tool := loop.tools.get("message"):
        if isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
            return None
    return mk_out(final_content)


async def process_message(
    loop: Any,
    *,
    msg: "InboundMessage",
    session_key: str | None = None,
    on_progress: Callable[[str], Any] | None = None,
) -> OutboundMessage | None:
    """Process one inbound message through system/command/regular pathways."""
    if msg.channel == "system":
        return await process_system_message(loop, msg)

    preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
    logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)
    reply_to_id = resolve_reply_to(msg.metadata)

    def mk_out(content: str, *, metadata: dict[str, Any] | None = None) -> OutboundMessage:
        return make_outbound(
            msg=msg,
            content=content,
            reply_to_id=reply_to_id,
            metadata=metadata,
        )

    key = session_key or msg.session_key
    session = get_or_create_session(loop, session_key=key)

    handled = await try_handle_slash_command(loop, msg=msg, session=session, mk_out=mk_out)
    if handled is not None:
        return handled

    maybe_schedule_consolidation(loop, session)
    return await execute_regular_message_turn(
        loop,
        msg=msg,
        session=session,
        reply_to_id=reply_to_id,
        on_progress=on_progress,
        mk_out=mk_out,
    )


async def handle_inbound_message(loop: Any, msg: "InboundMessage") -> None:
    """Handle one inbound message including timeout, publish, error, and cleanup."""
    try:
        response = await asyncio.wait_for(
            process_message(loop, msg=msg),
            timeout=float(loop._turn_timeout_seconds),
        )
        if response is not None:
            await loop.bus.publish_outbound(response)
        elif msg.channel == "cli":
            await loop.bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="",
                    metadata=msg.metadata or {},
                )
            )
    except Exception as e:
        logger.error("Error processing message: {}", e)
        await loop.bus.publish_outbound(
            OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=loop._format_user_error(e, user_message=msg.content),
                reply_to=resolve_reply_to(msg.metadata),
                metadata=msg.metadata or {},
            )
        )
    finally:
        loop._maybe_release_memory(active_session_key=msg.session_key)


async def process_direct_message(
    loop: Any,
    *,
    content: str,
    session_key: str,
    channel: str,
    chat_id: str,
    on_progress: Callable[[str], Any] | None = None,
) -> str:
    """Process one direct turn for CLI/cron style invocations."""
    msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
    try:
        response = await asyncio.wait_for(
            loop._process_message(msg, session_key=session_key, on_progress=on_progress),
            timeout=float(loop._turn_timeout_seconds),
        )
        return response.content if response else ""
    except asyncio.TimeoutError:
        error = TimeoutError(f"turn timed out after {loop._turn_timeout_seconds}s")
        return loop._format_user_error(error, user_message=content)
    except Exception as e:
        logger.error("Error in process_direct: {}", e)
        return loop._format_user_error(e, user_message=content)
    finally:
        loop._maybe_release_memory(active_session_key=session_key)
