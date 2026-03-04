"""Cron command handlers extracted from CLI commands."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime as _dt
from zoneinfo import ZoneInfo

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from orbitclaw.app.cli.runtime_wiring import build_agent_loop, make_provider
from orbitclaw.core.bus.queue import MessageBus
from orbitclaw.platform.config.loader import get_data_dir, load_config
from orbitclaw.services.cron.service import CronService
from orbitclaw.services.cron.types import CronJob, CronSchedule


def cron_list_command(*, all_jobs: bool, console: Console) -> None:
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    jobs = service.list_jobs(include_disabled=all_jobs)
    if not jobs:
        console.print("No scheduled jobs.")
        return

    table = Table(title="Scheduled Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Next Run")

    for job in jobs:
        if job.schedule.kind == "every":
            sched = f"every {(job.schedule.every_ms or 0) // 1000}s"
        elif job.schedule.kind == "cron":
            sched = f"{job.schedule.expr or ''} ({job.schedule.tz})" if job.schedule.tz else (job.schedule.expr or "")
        else:
            sched = "one-time"

        next_run = ""
        if job.state.next_run_at_ms:
            ts = job.state.next_run_at_ms / 1000
            try:
                tz = ZoneInfo(job.schedule.tz) if job.schedule.tz else None
                next_run = _dt.fromtimestamp(ts, tz).strftime("%Y-%m-%d %H:%M")
            except Exception:
                next_run = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))

        status = "[green]enabled[/green]" if job.enabled else "[dim]disabled[/dim]"
        table.add_row(job.id, job.name, sched, status, next_run)

    console.print(table)


def cron_add_command(
    *,
    name: str,
    message: str,
    every: int | None,
    cron_expr: str | None,
    tz: str | None,
    at: str | None,
    deliver: bool,
    to: str | None,
    channel: str | None,
    console: Console,
) -> None:
    if tz and not cron_expr:
        console.print("[red]Error: --tz can only be used with --cron[/red]")
        raise typer.Exit(1)

    if every:
        schedule = CronSchedule(kind="every", every_ms=every * 1000)
    elif cron_expr:
        schedule = CronSchedule(kind="cron", expr=cron_expr, tz=tz)
    elif at:
        import datetime

        dt = datetime.datetime.fromisoformat(at)
        schedule = CronSchedule(kind="at", at_ms=int(dt.timestamp() * 1000))
    else:
        console.print("[red]Error: Must specify --every, --cron, or --at[/red]")
        raise typer.Exit(1)

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    try:
        job = service.add_job(
            name=name,
            schedule=schedule,
            message=message,
            deliver=deliver,
            to=to,
            channel=channel,
        )
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e

    console.print(f"[green]✓[/green] Added job '{job.name}' ({job.id})")


def cron_remove_command(*, job_id: str, console: Console) -> None:
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    if service.remove_job(job_id):
        console.print(f"[green]✓[/green] Removed job {job_id}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


def cron_enable_command(*, job_id: str, disable: bool, console: Console) -> None:
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    job = service.enable_job(job_id, enabled=not disable)
    if job:
        status = "disabled" if disable else "enabled"
        console.print(f"[green]✓[/green] Job '{job.name}' {status}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


def cron_run_command(
    *,
    job_id: str,
    force: bool,
    console: Console,
    print_agent_response,
) -> None:
    logger.disable("orbitclaw")

    config = load_config()
    provider = make_provider(config)
    bus = MessageBus(
        inbound_maxsize=config.agents.defaults.inbound_queue_maxsize,
        outbound_maxsize=config.agents.defaults.outbound_queue_maxsize,
    )
    agent_loop = build_agent_loop(
        config=config,
        bus=bus,
        provider=provider,
    )

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    result_holder: list[str | None] = []

    async def on_job(job: CronJob) -> str | None:
        response = await agent_loop.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "cli",
            chat_id=job.payload.to or "direct",
        )
        result_holder.append(response)
        return response

    service.on_job = on_job

    async def run():
        return await service.run_job(job_id, force=force)

    if asyncio.run(run()):
        console.print("[green]✓[/green] Job executed")
        if result_holder:
            print_agent_response(result_holder[0] or "", render_markdown=True)
    else:
        console.print(f"[red]Failed to run job {job_id}[/red]")

