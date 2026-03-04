"""Gateway command runtime entry for CLI."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Callable

from orbitclaw.app.cli.runtime_wiring import (
    GatewayRuntimeState,
    gateway_reload_poll_seconds,
    print_gateway_runtime_summary,
    start_gateway_runtime,
    stop_gateway_runtime,
    task_exit_reason,
)
from orbitclaw.platform.config.schema import Config


def gateway_state_heartbeat_seconds() -> float:
    """Heartbeat interval for writing `running` gateway state file updates."""
    raw = (os.environ.get("ORBITCLAW_GATEWAY_STATE_HEARTBEAT_SECONDS") or "4.0").strip()
    try:
        value = float(raw)
    except ValueError:
        return 4.0
    return max(1.0, value)


def gateway_command(
    *,
    port: int,
    verbose: bool,
    console: Any,
    logo: str,
    ensure_runtime_dependencies: Callable[[Config], None],
) -> None:
    """Start the orbitclaw gateway."""
    from loguru import logger

    from orbitclaw.app.gateway.control import (
        compute_runtime_config_fingerprint,
        get_gateway_runtime_state_path,
        write_gateway_runtime_state,
    )
    from orbitclaw.platform.config.loader import (
        get_config_path,
        get_data_dir,
        load_config,
        load_config_strict,
    )

    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    console.print(f"{logo} Starting orbitclaw gateway on port {port}...")

    config_path = get_config_path()
    data_dir = get_data_dir()
    poll_seconds = gateway_reload_poll_seconds()
    heartbeat_seconds = gateway_state_heartbeat_seconds()
    state_path = get_gateway_runtime_state_path(config_path)
    console.print(f"[green]✓[/green] Hot reload: enabled (poll every {poll_seconds:.1f}s)")
    console.print(f"[dim]Gateway runtime heartbeat write: every {heartbeat_seconds:.1f}s[/dim]")
    console.print(f"[dim]Gateway state file: {state_path}[/dim]")

    async def run() -> None:
        state: GatewayRuntimeState | None = None
        fingerprint = ""
        failed_fingerprint: str | None = None
        last_running_write = 0.0

        def _write_state(*, status: str, note: str = "") -> None:
            nonlocal last_running_write
            write_gateway_runtime_state(
                config_path,
                fingerprint=fingerprint,
                status=status,
                note=note,
            )
            if status == "running":
                last_running_write = time.monotonic()

        try:
            if config_path.exists():
                config = load_config_strict(config_path, apply_profiles=True, resolve_env=True)
            else:
                config = load_config(config_path, apply_profiles=True, resolve_env=True)
            ensure_runtime_dependencies(config)
            state = await start_gateway_runtime(config, data_dir=data_dir)
            print_gateway_runtime_summary(state, console=console)
            fingerprint = compute_runtime_config_fingerprint(config_path)
            _write_state(status="running", note="gateway started")
            while True:
                await asyncio.sleep(poll_seconds)

                if state is None:
                    continue

                if (time.monotonic() - last_running_write) >= heartbeat_seconds:
                    _write_state(status="running")

                agent_issue = task_exit_reason(state.agent_task, name="agent loop")
                if agent_issue:
                    logger.error("Gateway runtime degraded: {}", agent_issue)
                    console.print(f"[yellow]↻[/yellow] Runtime degraded ({agent_issue}), reloading...")
                    _write_state(status="reloading", note=agent_issue)
                    old_config = state.config
                    await stop_gateway_runtime(state)
                    try:
                        state = await start_gateway_runtime(old_config, data_dir=data_dir)
                        print_gateway_runtime_summary(state, console=console)
                        _write_state(status="running", note="runtime recovered")
                    except Exception as restart_error:
                        logger.exception("Gateway recovery failed")
                        _write_state(status="error", note=f"runtime recovery failed: {restart_error}")
                        raise RuntimeError(f"gateway runtime recovery failed: {restart_error}") from restart_error
                    continue

                next_fingerprint = compute_runtime_config_fingerprint(config_path)
                if next_fingerprint == fingerprint:
                    continue
                if next_fingerprint == failed_fingerprint:
                    continue

                try:
                    next_config = load_config_strict(config_path, apply_profiles=True, resolve_env=True)
                    ensure_runtime_dependencies(next_config)
                except Exception as e:
                    failed_fingerprint = next_fingerprint
                    logger.warning("Skip reload due to invalid config/env snapshot: {}", e)
                    console.print(f"[yellow]Config reload skipped[/yellow]: {e}")
                    continue

                console.print("[cyan]↻[/cyan] Detected config/env change, reloading gateway runtime...")
                _write_state(status="reloading", note="config/env change detected")
                old_config = state.config
                await stop_gateway_runtime(state)
                try:
                    state = await start_gateway_runtime(next_config, data_dir=data_dir)
                    fingerprint = next_fingerprint
                    failed_fingerprint = None
                    print_gateway_runtime_summary(state, console=console)
                    console.print("[green]✓[/green] Gateway runtime reloaded")
                    _write_state(status="running", note="reload succeeded")
                except Exception as e:
                    logger.exception("Gateway reload failed, trying rollback")
                    console.print(f"[red]Reload failed[/red]: {e}")
                    console.print("[yellow]Attempting rollback to previous runtime...[/yellow]")
                    try:
                        state = await start_gateway_runtime(old_config, data_dir=data_dir)
                        print_gateway_runtime_summary(state, console=console)
                        fingerprint = compute_runtime_config_fingerprint(config_path)
                        console.print("[green]✓[/green] Rollback succeeded")
                        _write_state(status="running", note="rollback succeeded")
                    except Exception as rollback_error:
                        logger.exception("Gateway rollback failed")
                        _write_state(status="error", note=f"rollback failed: {rollback_error}")
                        raise RuntimeError(f"gateway rollback failed: {rollback_error}") from rollback_error
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        finally:
            if fingerprint:
                _write_state(status="stopped", note="gateway stopped")
            if state is not None:
                await stop_gateway_runtime(state)

    asyncio.run(run())
