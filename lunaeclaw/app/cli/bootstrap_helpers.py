"""CLI bootstrap helpers extracted from commands.py."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from rich.console import Console

from orbitclaw.platform.config.presets import apply_recommended_tool_defaults
from orbitclaw.platform.config.schema import Config


def apply_cli_recommended_tool_defaults(config: Config) -> None:
    """Apply shared defaults and CLI-specific profile presets."""
    apply_recommended_tool_defaults(config, include_profiles=True)


def claude_code_tool_requested(config: Config) -> bool:
    """Return True when claude_code tool is enabled in current tool policy."""
    if not bool(getattr(config.tools.claude_code, "enabled", False)):
        return False
    enabled = {str(t).strip().lower() for t in (config.tools.enabled or []) if str(t).strip()}
    return (not enabled) or ("claude_code" in enabled)


def detect_tmux_install_command() -> tuple[list[str], str] | tuple[None, str]:
    """Detect package manager command for installing tmux."""
    is_root = False
    try:
        is_root = hasattr(os, "geteuid") and os.geteuid() == 0
    except Exception:
        is_root = False
    sudo = shutil.which("sudo")
    sudo_prefix = [] if is_root else (["sudo", "-n"] if sudo else [])

    if shutil.which("brew"):
        return ["brew", "install", "tmux"], "brew"
    if shutil.which("apt-get"):
        if not is_root and not sudo:
            return None, "apt-get (sudo required)"
        return [*sudo_prefix, "apt-get", "install", "-y", "tmux"], "apt-get"
    if shutil.which("dnf"):
        if not is_root and not sudo:
            return None, "dnf (sudo required)"
        return [*sudo_prefix, "dnf", "install", "-y", "tmux"], "dnf"
    if shutil.which("yum"):
        if not is_root and not sudo:
            return None, "yum (sudo required)"
        return [*sudo_prefix, "yum", "install", "-y", "tmux"], "yum"
    if shutil.which("pacman"):
        if not is_root and not sudo:
            return None, "pacman (sudo required)"
        return [*sudo_prefix, "pacman", "-Sy", "--noconfirm", "tmux"], "pacman"
    if shutil.which("apk"):
        return ["apk", "add", "tmux"], "apk"
    return None, "no supported package manager found"


def ensure_claude_code_runtime_dependencies(config: Config, *, console: Console) -> None:
    """Best-effort startup dependency check for the claude_code tool."""
    if not claude_code_tool_requested(config):
        return

    ccfg = config.tools.claude_code
    tmux_cmd = (ccfg.tmux_command or "tmux").strip()
    claude_cmd = (ccfg.command or "claude").strip()

    def _cmd_exists(cmd: str) -> bool:
        if not cmd:
            return False
        if "/" in cmd or cmd.startswith("."):
            return Path(cmd).expanduser().exists()
        return shutil.which(cmd) is not None

    tmux_exists = _cmd_exists(tmux_cmd)
    if not tmux_exists:
        console.print(f"[yellow]Claude Code tool enabled but tmux is missing (`{tmux_cmd}`)[/yellow]")
        if bool(getattr(ccfg, "auto_install_tmux", True)):
            install_cmd, installer = detect_tmux_install_command()
            if install_cmd:
                console.print(f"[dim]Attempting to install tmux via {installer}: {' '.join(install_cmd)}[/dim]")
                try:
                    proc = subprocess.run(
                        install_cmd,
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=180,
                    )
                    if proc.returncode == 0 and _cmd_exists(tmux_cmd):
                        console.print("[green]✓[/green] tmux installed successfully")
                    else:
                        detail = (proc.stderr or proc.stdout or f"exit code {proc.returncode}").strip()
                        console.print(f"[red]Failed to auto-install tmux[/red]: {detail[:300]}")
                except Exception as exc:
                    console.print(f"[red]Failed to auto-install tmux[/red]: {exc}")
            else:
                console.print(f"[yellow]Cannot auto-install tmux[/yellow] ({installer}). Please install manually.")
        else:
            console.print("[dim]tools.claudeCode.autoInstallTmux=false, skipping auto-install[/dim]")

    if not _cmd_exists(claude_cmd):
        console.print(
            f"[yellow]Claude Code CLI not found (`{claude_cmd}`)[/yellow] — startup continues; "
            "`claude_code` tool will be unavailable until installed."
        )
