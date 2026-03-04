"""Channel command handlers extracted from CLI commands."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Callable

import typer
from rich.console import Console
from rich.table import Table

from lunaeclaw.platform.config.loader import load_config
from lunaeclaw.platform.utils.helpers import get_bridge_dir


def channels_status_command(
    *,
    console: Console,
    ensure_runtime_dependencies: Callable[..., None],
) -> None:
    config = load_config()
    ensure_runtime_dependencies(config, console=console)

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Configuration", style="yellow")

    wa = config.channels.whatsapp
    table.add_row("WhatsApp", "✓" if wa.enabled else "✗", wa.bridge_url)

    dc = config.channels.discord
    table.add_row("Discord", "✓" if dc.enabled else "✗", dc.gateway_url)

    fs = config.channels.feishu
    fs_config = f"app_id: {fs.app_id[:10]}..." if fs.app_id else "[dim]not configured[/dim]"
    table.add_row("Feishu", "✓" if fs.enabled else "✗", fs_config)

    mc = config.channels.mochat
    mc_base = mc.base_url or "[dim]not configured[/dim]"
    table.add_row("Mochat", "✓" if mc.enabled else "✗", mc_base)

    tg = config.channels.telegram
    tg_config = f"token: {tg.token[:10]}..." if tg.token else "[dim]not configured[/dim]"
    table.add_row("Telegram", "✓" if tg.enabled else "✗", tg_config)

    slack = config.channels.slack
    slack_config = "socket" if slack.app_token and slack.bot_token else "[dim]not configured[/dim]"
    table.add_row("Slack", "✓" if slack.enabled else "✗", slack_config)

    dt = config.channels.dingtalk
    dt_config = f"client_id: {dt.client_id[:10]}..." if dt.client_id else "[dim]not configured[/dim]"
    table.add_row("DingTalk", "✓" if dt.enabled else "✗", dt_config)

    qq = config.channels.qq
    qq_config = f"app_id: {qq.app_id[:10]}..." if qq.app_id else "[dim]not configured[/dim]"
    table.add_row("QQ", "✓" if qq.enabled else "✗", qq_config)

    em = config.channels.email
    em_config = em.imap_host if em.imap_host else "[dim]not configured[/dim]"
    table.add_row("Email", "✓" if em.enabled else "✗", em_config)

    console.print(table)


def get_bridge_dir_command(*, console: Console, logo: str) -> Path:
    """Get the bridge directory, setting it up if needed."""
    user_bridge = get_bridge_dir()
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge

    if not shutil.which("npm"):
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)

    pkg_bridge = Path(__file__).parent.parent / "bridge"
    src_bridge = Path(__file__).parent.parent.parent / "bridge"

    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge

    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall lunaeclaw")
        raise typer.Exit(1)

    console.print(f"{logo} Setting up bridge...")
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))

    try:
        console.print("  Installing dependencies...")
        subprocess.run(["npm", "install"], cwd=user_bridge, check=True, capture_output=True)
        console.print("  Building...")
        subprocess.run(["npm", "run", "build"], cwd=user_bridge, check=True, capture_output=True)
        console.print("[green]✓[/green] Bridge ready\n")
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Build failed: {e}[/red]")
        if e.stderr:
            console.print(f"[dim]{e.stderr.decode()[:500]}[/dim]")
        raise typer.Exit(1)

    return user_bridge


def channels_login_command(*, console: Console, logo: str) -> None:
    config = load_config()
    bridge_dir = get_bridge_dir_command(console=console, logo=logo)

    console.print(f"{logo} Starting bridge...")
    console.print("Scan the QR code to connect.\n")

    env = {**os.environ}
    if config.channels.whatsapp.bridge_token:
        env["BRIDGE_TOKEN"] = config.channels.whatsapp.bridge_token

    try:
        subprocess.run(["npm", "start"], cwd=bridge_dir, check=True, env=env)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Bridge failed: {e}[/red]")
    except FileNotFoundError:
        console.print("[red]npm not found. Please install Node.js.[/red]")

