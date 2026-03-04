"""CLI commands for lunaeclaw."""

import os
import select
import sys
from pathlib import Path

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markdown import Markdown
from rich.text import Text

from lunaeclaw import __logo__, __version__
from lunaeclaw.app.cli.agent_entry import run_agent_command
from lunaeclaw.app.cli.bootstrap_helpers import (
    apply_cli_recommended_tool_defaults as _apply_cli_recommended_tool_defaults,
)
from lunaeclaw.app.cli.bootstrap_helpers import (
    ensure_claude_code_runtime_dependencies as _ensure_claude_code_runtime_dependencies,
)
from lunaeclaw.app.cli.channels_entry import (
    channels_login_command,
    channels_status_command,
)
from lunaeclaw.app.cli.cron_entry import (
    cron_add_command,
    cron_enable_command,
    cron_list_command,
    cron_remove_command,
    cron_run_command,
)
from lunaeclaw.app.cli.gateway_entry import gateway_command
from lunaeclaw.app.cli.provider_entry import provider_login_command
from lunaeclaw.app.cli.setup_entry import (
    bootstrap_runtime_for_webui as _bootstrap_runtime_for_webui,
)
from lunaeclaw.app.cli.setup_entry import (
    onboard_command,
)

app = typer.Typer(
    name="lunaeclaw",
    help=f"{__logo__} lunaeclaw - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}

# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _flush_pending_tty_input() -> None:
    """Drop unread keypresses typed while the model was generating output."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios
        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return


def _restore_terminal() -> None:
    """Restore terminal to its original state (echo, line buffering, etc.)."""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


def _init_prompt_session() -> None:
    """Create the prompt_toolkit session with persistent file history."""
    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    # Save terminal state so we can restore it on exit
    try:
        import termios
        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    from lunaeclaw.platform.utils.helpers import get_cli_history_file
    history_file = get_cli_history_file()

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(history_file)),
        enable_open_in_editor=False,
        multiline=False,   # Enter submits (single line mode)
    )


def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Render assistant response with consistent terminal styling."""
    content = response or ""
    body = Markdown(content) if render_markdown else Text(content)
    console.print()
    console.print(f"[cyan]{__logo__} lunaeclaw[/cyan]")
    console.print(body)
    console.print()


def _is_exit_command(command: str) -> bool:
    """Return True when input should end interactive chat."""
    return command.lower() in EXIT_COMMANDS


async def _read_interactive_input_async() -> str:
    """Read user input using prompt_toolkit (handles paste, history, display).

    prompt_toolkit natively handles:
    - Multiline paste (bracketed paste mode)
    - History navigation (up/down arrows)
    - Clean display (no ghost characters or artifacts)
    """
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc



def version_callback(value: bool):
    if value:
        console.print(f"{__logo__} lunaeclaw v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """lunaeclaw - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard():
    """Initialize lunaeclaw configuration and workspace."""
    onboard_command(
        console=console,
        logo=__logo__,
        apply_recommended_tool_defaults=_apply_cli_recommended_tool_defaults,
    )


# ============================================================================
# Gateway / Server
# ============================================================================


@app.command()
def gateway(
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the lunaeclaw gateway."""
    gateway_command(
        port=port,
        verbose=verbose,
        console=console,
        logo=__logo__,
        ensure_runtime_dependencies=lambda config: _ensure_claude_code_runtime_dependencies(
            config, console=console
        ),
    )




# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown", help="Render assistant output as Markdown"),
    logs: bool = typer.Option(False, "--logs/--no-logs", help="Show lunaeclaw runtime logs during chat"),
):
    """Interact with the agent directly."""
    run_agent_command(
        message=message,
        session_id=session_id,
        markdown=markdown,
        logs=logs,
        logo=__logo__,
        console=console,
        ensure_runtime_dependencies=_ensure_claude_code_runtime_dependencies,
        print_agent_response=_print_agent_response,
        init_prompt_session=_init_prompt_session,
        flush_pending_tty_input=_flush_pending_tty_input,
        restore_terminal=_restore_terminal,
        is_exit_command=_is_exit_command,
        read_interactive_input_async=_read_interactive_input_async,
    )


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    channels_status_command(
        console=console,
        ensure_runtime_dependencies=_ensure_claude_code_runtime_dependencies,
    )


@channels_app.command("login")
def channels_login():
    """Link device via QR code."""
    channels_login_command(console=console, logo=__logo__)


# ============================================================================
# Cron Commands
# ============================================================================

cron_app = typer.Typer(help="Manage scheduled tasks")
app.add_typer(cron_app, name="cron")


@cron_app.command("list")
def cron_list(
    all: bool = typer.Option(False, "--all", "-a", help="Include disabled jobs"),
):
    """List scheduled jobs."""
    cron_list_command(all_jobs=all, console=console)


@cron_app.command("add")
def cron_add(
    name: str = typer.Option(..., "--name", "-n", help="Job name"),
    message: str = typer.Option(..., "--message", "-m", help="Message for agent"),
    every: int = typer.Option(None, "--every", "-e", help="Run every N seconds"),
    cron_expr: str = typer.Option(None, "--cron", "-c", help="Cron expression (e.g. '0 9 * * *')"),
    tz: str | None = typer.Option(None, "--tz", help="IANA timezone for cron (e.g. 'America/Vancouver')"),
    at: str = typer.Option(None, "--at", help="Run once at time (ISO format)"),
    deliver: bool = typer.Option(False, "--deliver", "-d", help="Deliver response to channel"),
    to: str = typer.Option(None, "--to", help="Recipient for delivery"),
    channel: str = typer.Option(None, "--channel", help="Channel for delivery (e.g. 'telegram', 'whatsapp')"),
):
    """Add a scheduled job."""
    cron_add_command(
        name=name,
        message=message,
        every=every,
        cron_expr=cron_expr,
        tz=tz,
        at=at,
        deliver=deliver,
        to=to,
        channel=channel,
        console=console,
    )


@cron_app.command("remove")
def cron_remove(
    job_id: str = typer.Argument(..., help="Job ID to remove"),
):
    """Remove a scheduled job."""
    cron_remove_command(job_id=job_id, console=console)


@cron_app.command("enable")
def cron_enable(
    job_id: str = typer.Argument(..., help="Job ID"),
    disable: bool = typer.Option(False, "--disable", help="Disable instead of enable"),
):
    """Enable or disable a job."""
    cron_enable_command(job_id=job_id, disable=disable, console=console)


@cron_app.command("run")
def cron_run(
    job_id: str = typer.Argument(..., help="Job ID to run"),
    force: bool = typer.Option(False, "--force", "-f", help="Run even if disabled"),
):
    """Manually run a job."""
    cron_run_command(
        job_id=job_id,
        force=force,
        console=console,
        print_agent_response=_print_agent_response,
    )


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show lunaeclaw status."""
    from lunaeclaw.app.cli.diagnostics_commands import run_status

    run_status(console, __logo__)


@app.command()
def doctor():
    """Diagnose configuration/tooling issues and suggest fixes."""
    from lunaeclaw.app.cli.diagnostics_commands import run_doctor

    run_doctor(console, __logo__)


@app.command()
def webui(
    host: str = typer.Option("127.0.0.1", help="Bind host (default localhost for safety)"),
    port: int = typer.Option(18791, help="Bind port for the local web UI"),
    config_path: Path | None = typer.Option(None, "--config", help="Optional config file path"),
    open_browser: bool = typer.Option(False, help="Open browser automatically after startup"),
    path_token: str | None = typer.Option(
        None,
        "--path-token",
        help="Optional Web UI path token (URL secret suffix, no login popup). Can also use LUNAECLAW_WEBUI_PATH_TOKEN.",
        envvar="LUNAECLAW_WEBUI_PATH_TOKEN",
    ),
):
    """Run a lightweight local web UI for config / MCP / skills / channels management."""
    from lunaeclaw.app.webui.server import run_webui

    _bootstrap_runtime_for_webui(
        config_path,
        console=console,
        apply_recommended_tool_defaults=_apply_cli_recommended_tool_defaults,
    )
    run_webui(host=host, port=port, config_path=config_path, open_browser=open_browser, path_token=path_token)


# ============================================================================
# OAuth Login
# ============================================================================

provider_app = typer.Typer(help="Manage providers")
app.add_typer(provider_app, name="provider")

@provider_app.command("login")
def provider_login(
    provider: str = typer.Argument(..., help="OAuth provider (e.g. 'openai-codex', 'github-copilot')"),
):
    """Authenticate with an OAuth provider."""
    provider_login_command(provider=provider, console=console, logo=__logo__)


if __name__ == "__main__":
    app()
