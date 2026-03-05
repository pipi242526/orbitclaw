"""Gateway command runtime entry for CLI."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Callable

from lunaeclaw.app.cli.runtime_wiring import (
    GatewayRuntimeState,
    gateway_reload_poll_seconds,
    print_gateway_runtime_summary,
    start_gateway_runtime,
    stop_gateway_runtime,
    task_exit_reason,
)
from lunaeclaw.platform.config.schema import Config


def _format_wait_reason(exc: Exception) -> str:
    """Format startup/reload failures into user-actionable waiting reasons."""
    try:
        from click.exceptions import Exit as ClickExit

        if isinstance(exc, ClickExit):
            exit_code = getattr(exc, "exit_code", 1)
            return (
                "provider/model config invalid: missing API key or endpoint; "
                "update ~/.lunaeclaw/config.json and env files "
                f"(exit={exit_code})"
            )
    except Exception:  # pragma: no cover
        pass

    text = str(exc).strip()
    if not text or text.isdigit():
        return (
            "provider/model config invalid: missing API key or endpoint; "
            "update ~/.lunaeclaw/config.json and env files"
        )
    return text


def gateway_state_heartbeat_seconds() -> float:
    """Heartbeat interval for writing `running` gateway state file updates."""
    raw = (os.environ.get("LUNAECLAW_GATEWAY_STATE_HEARTBEAT_SECONDS") or "4.0").strip()
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
    """Start the lunaeclaw gateway."""
    from loguru import logger

    from lunaeclaw.app.gateway.control import (
        compute_runtime_config_fingerprint,
        get_gateway_runtime_state_path,
        write_gateway_runtime_state,
    )
    from lunaeclaw.platform.config.loader import (
        get_config_path,
        get_data_dir,
        load_config,
        load_config_strict,
    )

    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)

    console.print(f"{logo} Starting lunaeclaw gateway on port {port}...")

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

        async def _start_runtime(config: Config, *, note: str) -> GatewayRuntimeState | None:
            nonlocal fingerprint, failed_fingerprint
            try:
                ensure_runtime_dependencies(config)
                next_state = await start_gateway_runtime(config, data_dir=data_dir)
                print_gateway_runtime_summary(next_state, console=console)
                fingerprint = compute_runtime_config_fingerprint(config_path)
                failed_fingerprint = None
                _write_state(status="running", note=note)
                return next_state
            except Exception as exc:
                fingerprint = compute_runtime_config_fingerprint(config_path)
                failed_fingerprint = fingerprint
                reason = _format_wait_reason(exc)
                logger.warning("Gateway runtime waiting for valid config/dependencies: {}", reason)
                console.print(f"[yellow]Gateway waiting for valid config[/yellow]: {reason}")
                _write_state(status="waiting_config", note=reason)
                return None

        def _load_config_snapshot() -> Config:
            if config_path.exists():
                return load_config_strict(config_path, apply_profiles=True, resolve_env=True)
            return load_config(config_path, apply_profiles=True, resolve_env=True)

        try:
            try:
                config = _load_config_snapshot()
            except Exception as exc:
                fingerprint = compute_runtime_config_fingerprint(config_path)
                failed_fingerprint = fingerprint
                reason = _format_wait_reason(exc)
                logger.warning("Gateway config snapshot invalid: {}", reason)
                console.print(f"[yellow]Gateway waiting for valid config[/yellow]: {reason}")
                _write_state(status="waiting_config", note=reason)
            else:
                state = await _start_runtime(config, note="gateway started")
            while True:
                await asyncio.sleep(poll_seconds)

                if state is None:
                    next_fingerprint = compute_runtime_config_fingerprint(config_path)
                    if next_fingerprint == failed_fingerprint:
                        continue
                    try:
                        next_config = _load_config_snapshot()
                    except Exception as exc:
                        failed_fingerprint = next_fingerprint
                        reason = _format_wait_reason(exc)
                        logger.warning("Gateway still waiting for valid config snapshot: {}", reason)
                        _write_state(status="waiting_config", note=reason)
                        continue
                    state = await _start_runtime(next_config, note="gateway started after config update")
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
                    state = await _start_runtime(old_config, note="runtime recovered")
                    continue

                next_fingerprint = compute_runtime_config_fingerprint(config_path)
                if next_fingerprint == fingerprint:
                    continue
                if next_fingerprint == failed_fingerprint:
                    continue

                try:
                    next_config = load_config_strict(config_path, apply_profiles=True, resolve_env=True)
                except Exception as e:
                    failed_fingerprint = next_fingerprint
                    logger.warning("Skip reload due to invalid config/env snapshot: {}", e)
                    console.print(f"[yellow]Config reload skipped[/yellow]: {e}")
                    _write_state(status="waiting_config", note=str(e))
                    continue

                console.print("[cyan]↻[/cyan] Detected config/env change, reloading gateway runtime...")
                _write_state(status="reloading", note="config/env change detected")
                old_config = state.config
                await stop_gateway_runtime(state)
                state = await _start_runtime(next_config, note="reload succeeded")
                if state is not None:
                    console.print("[green]✓[/green] Gateway runtime reloaded")
                    continue

                console.print("[yellow]Attempting rollback to previous runtime...[/yellow]")
                state = await _start_runtime(old_config, note="rollback succeeded")
                if state is not None:
                    console.print("[green]✓[/green] Rollback succeeded")
                else:
                    console.print("[yellow]Gateway waiting for valid config update before restart[/yellow]")
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        finally:
            if fingerprint:
                _write_state(status="stopped", note="gateway stopped")
            if state is not None:
                await stop_gateway_runtime(state)

    asyncio.run(run())
