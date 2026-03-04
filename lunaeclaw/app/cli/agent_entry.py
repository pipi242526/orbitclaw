"""Agent command runtime entry for CLI."""

from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Awaitable, Callable
from contextlib import nullcontext

from loguru import logger
from rich.console import Console

from lunaeclaw.app.cli.runtime_wiring import build_agent_loop, make_provider
from lunaeclaw.core.bus.events import InboundMessage
from lunaeclaw.core.bus.queue import MessageBus
from lunaeclaw.platform.config.loader import get_data_dir, load_config
from lunaeclaw.services.cron.service import CronService


def run_agent_command(
    *,
    message: str | None,
    session_id: str,
    markdown: bool,
    logs: bool,
    logo: str,
    console: Console,
    ensure_runtime_dependencies: Callable[..., None],
    print_agent_response: Callable[[str, bool], None],
    init_prompt_session: Callable[[], None],
    flush_pending_tty_input: Callable[[], None],
    restore_terminal: Callable[[], None],
    is_exit_command: Callable[[str], bool],
    read_interactive_input_async: Callable[[], Awaitable[str]],
) -> None:
    """Run agent command in single-message or interactive mode."""
    config = load_config()
    ensure_runtime_dependencies(config, console=console)

    bus = MessageBus(
        inbound_maxsize=config.agents.defaults.inbound_queue_maxsize,
        outbound_maxsize=config.agents.defaults.outbound_queue_maxsize,
    )
    provider = make_provider(config)
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    if logs:
        logger.enable("lunaeclaw")
    else:
        logger.disable("lunaeclaw")

    agent_loop = build_agent_loop(
        config=config,
        bus=bus,
        provider=provider,
        cron_service=cron,
    )

    def thinking_ctx():
        if logs:
            return nullcontext()
        return console.status("[dim]lunaeclaw is thinking...[/dim]", spinner="dots")

    async def cli_progress(content: str) -> None:
        console.print(f"  [dim]↳ {content}[/dim]")

    if message:
        async def run_once():
            with thinking_ctx():
                response = await agent_loop.process_direct(message, session_id, on_progress=cli_progress)
            print_agent_response(response, render_markdown=markdown)
            await agent_loop.close_mcp()

        asyncio.run(run_once())
        return

    init_prompt_session()
    console.print(f"{logo} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n")

    if ":" in session_id:
        cli_channel, cli_chat_id = session_id.split(":", 1)
    else:
        cli_channel, cli_chat_id = "cli", session_id

    def exit_on_sigint(signum, frame):
        _ = (signum, frame)
        restore_terminal()
        console.print("\nGoodbye!")
        os._exit(0)

    signal.signal(signal.SIGINT, exit_on_sigint)

    async def run_interactive():
        bus_task = asyncio.create_task(agent_loop.run())
        turn_done = asyncio.Event()
        turn_done.set()
        turn_response: list[str] = []

        async def consume_outbound():
            while True:
                try:
                    msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
                    if msg.metadata.get("_progress"):
                        console.print(f"  [dim]↳ {msg.content}[/dim]")
                    elif not turn_done.is_set():
                        if msg.content:
                            turn_response.append(msg.content)
                        turn_done.set()
                    elif msg.content:
                        console.print()
                        print_agent_response(msg.content, render_markdown=markdown)
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

        outbound_task = asyncio.create_task(consume_outbound())
        try:
            while True:
                try:
                    flush_pending_tty_input()
                    user_input = await read_interactive_input_async()
                    command = user_input.strip()
                    if not command:
                        continue

                    if is_exit_command(command):
                        restore_terminal()
                        console.print("\nGoodbye!")
                        break

                    turn_done.clear()
                    turn_response.clear()

                    await bus.publish_inbound(
                        InboundMessage(
                            channel=cli_channel,
                            sender_id="user",
                            chat_id=cli_chat_id,
                            content=user_input,
                        )
                    )

                    with thinking_ctx():
                        await turn_done.wait()

                    if turn_response:
                        print_agent_response(turn_response[0], render_markdown=markdown)
                except KeyboardInterrupt:
                    restore_terminal()
                    console.print("\nGoodbye!")
                    break
                except EOFError:
                    restore_terminal()
                    console.print("\nGoodbye!")
                    break
        finally:
            agent_loop.stop()
            outbound_task.cancel()
            await asyncio.gather(bus_task, outbound_task, return_exceptions=True)
            await agent_loop.close_mcp()

    asyncio.run(run_interactive())

