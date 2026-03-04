"""Runtime wiring helpers shared by CLI gateway/agent entry points."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer
from rich.console import Console

from orbitclaw.capabilities.channels.manager import ChannelManager
from orbitclaw.core.agent.orchestrator import build_agent_loop as _build_agent_loop
from orbitclaw.core.bus.events import OutboundMessage
from orbitclaw.core.bus.queue import MessageBus
from orbitclaw.platform.config.schema import Config
from orbitclaw.services.cron.service import CronService
from orbitclaw.services.cron.types import CronJob
from orbitclaw.services.heartbeat.service import HeartbeatService
from orbitclaw.services.session.manager import SessionManager

_console = Console()


def make_single_provider(config: Config, model: str):
    """Create a provider for a concrete model (non-endpoint-routed path)."""
    from orbitclaw.platform.providers.custom_provider import CustomProvider
    from orbitclaw.platform.providers.litellm_provider import LiteLLMProvider
    from orbitclaw.platform.providers.openai_codex_provider import OpenAICodexProvider
    from orbitclaw.platform.providers.registry import find_by_name

    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        return OpenAICodexProvider(default_model=model)

    if provider_name == "custom":
        return CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
        )

    spec = find_by_name(provider_name)
    if not model.startswith("bedrock/") and not (p and p.api_key) and not (spec and spec.is_oauth):
        _console.print("[red]Error: No API key configured.[/red]")
        _console.print("Set one in ~/.orbitclaw/config.json under providers section")
        raise typer.Exit(1)

    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=provider_name,
    )


def make_provider(config: Config):
    """Create provider from config; supports endpoint router mode."""
    model = config.agents.defaults.model
    if config.providers.endpoints:
        from orbitclaw.platform.providers.router_provider import RouterProvider

        return RouterProvider(
            default_model=model,
            endpoints=config.providers.endpoints,
            fallback_factory=lambda fallback_model: make_single_provider(config, fallback_model),
        )
    return make_single_provider(config, model)


def build_agent_loop(
    *,
    config: Config,
    bus,
    provider,
    cron_service=None,
    session_manager=None,
):
    """Create AgentLoop from shared config defaults."""
    return _build_agent_loop(
        config=config,
        bus=bus,
        provider=provider,
        cron_service=cron_service,
        session_manager=session_manager,
    )


@dataclass
class GatewayRuntimeState:
    config: Config
    bus: Any
    agent: Any
    channels: Any
    cron: Any
    heartbeat: Any
    agent_task: asyncio.Task
    channels_task: asyncio.Task


def gateway_reload_poll_seconds() -> float:
    raw = (os.environ.get("ORBITCLAW_GATEWAY_RELOAD_POLL_SECONDS") or "2.0").strip()
    try:
        value = float(raw)
    except ValueError:
        return 2.0
    return max(0.5, value)


def task_exit_reason(task: asyncio.Task, *, name: str) -> str | None:
    if not task.done():
        return None
    if task.cancelled():
        return f"{name} cancelled"
    exc = task.exception()
    if exc is None:
        return f"{name} exited unexpectedly"
    return f"{name} failed: {exc}"


async def start_gateway_runtime(config: Config, *, data_dir: Path) -> GatewayRuntimeState:
    bus = MessageBus(
        inbound_maxsize=config.agents.defaults.inbound_queue_maxsize,
        outbound_maxsize=config.agents.defaults.outbound_queue_maxsize,
    )
    provider = make_provider(config)
    session_manager = SessionManager(
        config.workspace_path,
        max_cache_entries=config.agents.defaults.session_cache_max_entries,
    )
    cron_store_path = data_dir / "cron" / "jobs.json"
    cron = CronService(cron_store_path)
    agent = build_agent_loop(
        config=config,
        bus=bus,
        provider=provider,
        cron_service=cron,
        session_manager=session_manager,
    )

    async def on_cron_job(job: CronJob) -> str | None:
        response = await agent.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "cli",
            chat_id=job.payload.to or "direct",
        )
        if job.payload.deliver and job.payload.to:
            await bus.publish_outbound(
                OutboundMessage(
                    channel=job.payload.channel or "cli",
                    chat_id=job.payload.to,
                    content=response or "",
                )
            )
        return response

    cron.on_job = on_cron_job

    async def on_heartbeat(prompt: str) -> str:
        return await agent.process_direct(prompt, session_key="heartbeat")

    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        on_heartbeat=on_heartbeat,
        interval_s=30 * 60,
        enabled=True,
    )
    channels = ChannelManager(config, bus)

    await cron.start()
    await heartbeat.start()
    agent_task = asyncio.create_task(agent.run(), name="orbitclaw.core.agent.run")
    channels_task = asyncio.create_task(channels.start_all(), name="orbitclaw.capabilities.channels.start_all")

    return GatewayRuntimeState(
        config=config,
        bus=bus,
        agent=agent,
        channels=channels,
        cron=cron,
        heartbeat=heartbeat,
        agent_task=agent_task,
        channels_task=channels_task,
    )


async def stop_gateway_runtime(state: GatewayRuntimeState) -> None:
    state.agent.stop()
    state.heartbeat.stop()
    state.cron.stop()
    await state.channels.stop_all()
    await state.agent.close_mcp()
    for task in (state.agent_task, state.channels_task):
        if not task.done():
            task.cancel()
    await asyncio.gather(state.agent_task, state.channels_task, return_exceptions=True)


def print_gateway_runtime_summary(state: GatewayRuntimeState, *, console: Console) -> None:
    if state.channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(state.channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")

    cron_status = state.cron.status()
    if cron_status.get("jobs", 0) > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")
    console.print("[green]✓[/green] Heartbeat: every 30m")
