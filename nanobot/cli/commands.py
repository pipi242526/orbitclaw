"""CLI commands for nanobot."""

import asyncio
import os
import shutil
import signal
import subprocess
from pathlib import Path
import select
import sys

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout

from nanobot import __version__, __logo__
from nanobot.config.schema import Config, MCPServerConfig, ProfileOverridesConfig

app = typer.Typer(
    name="nanobot",
    help=f"{__logo__} nanobot - Personal AI Assistant",
    no_args_is_help=True,
)

console = Console()
EXIT_COMMANDS = {"exit", "quit", "/exit", "/quit", ":q"}

# ---------------------------------------------------------------------------
# CLI input: prompt_toolkit for editing, paste, history, and display
# ---------------------------------------------------------------------------

_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None  # original termios settings, restored on exit


def _merge_unique(items: list[str], additions: list[str]) -> list[str]:
    """Append strings while preserving order and removing duplicates."""
    out: list[str] = []
    for value in [*items, *additions]:
        if value and value not in out:
            out.append(value)
    return out


def _apply_recommended_tool_defaults(config: Config) -> None:
    """Seed lightweight MCP/tool defaults for first-time users without overriding custom settings."""
    tools = config.tools

    # Prefer Exa MCP for search.
    if not tools.web.search.provider or tools.web.search.provider not in {"exa_mcp", "disabled"}:
        tools.web.search.provider = "exa_mcp"

    if "exa" not in tools.mcp_servers:
        tools.mcp_servers["exa"] = MCPServerConfig(
            url="https://mcp.exa.ai/mcp?tools=web_search_exa,get_code_context_exa"
        )

    if "docloader" not in tools.mcp_servers:
        tools.mcp_servers["docloader"] = MCPServerConfig(
            command="uvx",
            args=["awslabs.document-loader-mcp-server@latest"],
            env={"FASTMCP_LOG_LEVEL": "ERROR"},
        )

    tools.mcp_enabled_servers = _merge_unique(tools.mcp_enabled_servers, ["exa", "docloader"])
    tools.mcp_enabled_tools = _merge_unique(
        tools.mcp_enabled_tools,
        ["web_search_exa", "get_code_context_exa", "read_document", "read_image"],
    )

    # Keep built-in tool names stable while allowing direct calls to MCP-backed helpers.
    tools.aliases.setdefault("code_search", "mcp_exa_get_code_context_exa")
    tools.aliases.setdefault("doc_read", "mcp_docloader_read_document")
    tools.aliases.setdefault("image_read", "mcp_docloader_read_image")

    # Seed lightweight usage profiles; users can switch by setting profiles.active.
    profiles = config.profiles
    if "cn_dev" not in profiles.items:
        profiles.items["cn_dev"] = ProfileOverridesConfig(
            tools={"web": {"search": {"provider": "exa_mcp"}}},
            skills={"disabled": ["clawhub", "tmux", "summarize", "weather"]},
        )
    if "research" not in profiles.items:
        profiles.items["research"] = ProfileOverridesConfig(
            tools={"web": {"search": {"provider": "exa_mcp"}}},
            skills={"disabled": ["clawhub", "tmux"]},
        )
    if "offline" not in profiles.items:
        profiles.items["offline"] = ProfileOverridesConfig(
            tools={"web": {"search": {"provider": "disabled"}}},
            skills={"disabled": ["clawhub", "weather"]},
        )
    if not profiles.active:
        profiles.active = "cn_dev"


def _claude_code_tool_requested(config: Config) -> bool:
    if not bool(getattr(config.tools.claude_code, "enabled", False)):
        return False
    enabled = {str(t).strip().lower() for t in (config.tools.enabled or []) if str(t).strip()}
    return (not enabled) or ("claude_code" in enabled)


def _detect_tmux_install_command() -> tuple[list[str], str] | tuple[None, str]:
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


def _ensure_claude_code_runtime_dependencies(config: Config) -> None:
    """Best-effort startup dependency check for the claude_code tool."""
    if not _claude_code_tool_requested(config):
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
            install_cmd, installer = _detect_tmux_install_command()
            if install_cmd:
                console.print(f"[dim]Attempting to install tmux via {installer}: {' '.join(install_cmd)}[/dim]")
                try:
                    p = subprocess.run(
                        install_cmd,
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=180,
                    )
                    if p.returncode == 0 and _cmd_exists(tmux_cmd):
                        console.print("[green]✓[/green] tmux installed successfully")
                        tmux_exists = True
                    else:
                        detail = (p.stderr or p.stdout or f"exit code {p.returncode}").strip()
                        console.print(f"[red]Failed to auto-install tmux[/red]: {detail[:300]}")
                except Exception as e:
                    console.print(f"[red]Failed to auto-install tmux[/red]: {e}")
            else:
                console.print(f"[yellow]Cannot auto-install tmux[/yellow] ({installer}). Please install manually.")
        else:
            console.print("[dim]tools.claudeCode.autoInstallTmux=false, skipping auto-install[/dim]")

    if not _cmd_exists(claude_cmd):
        console.print(
            f"[yellow]Claude Code CLI not found (`{claude_cmd}`)[/yellow] — startup continues; "
            "`claude_code` tool will be unavailable until installed."
        )


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

    from nanobot.utils.helpers import get_cli_history_file
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
    console.print(f"[cyan]{__logo__} nanobot[/cyan]")
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
        console.print(f"{__logo__} nanobot v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        None, "--version", "-v", callback=version_callback, is_eager=True
    ),
):
    """nanobot - Personal AI Assistant."""
    pass


# ============================================================================
# Onboard / Setup
# ============================================================================


@app.command()
def onboard():
    """Initialize nanobot configuration and workspace."""
    from nanobot.config.loader import get_config_path, load_config, save_config
    from nanobot.config.schema import Config
    from nanobot.utils.helpers import (
        get_workspace_path,
        get_env_dir,
        get_env_file,
        get_mcp_home,
        get_global_skills_path,
    )
    
    config_path = get_config_path()
    
    if config_path.exists():
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        console.print("  [bold]y[/bold] = overwrite with defaults (existing values will be lost)")
        console.print("  [bold]N[/bold] = refresh config, keeping existing values and adding new fields")
        if typer.confirm("Overwrite?"):
            config = Config()
            _apply_recommended_tool_defaults(config)
            save_config(config)
            console.print(f"[green]✓[/green] Config reset to defaults at {config_path}")
        else:
            config = load_config(apply_profiles=False, resolve_env=False)
            _apply_recommended_tool_defaults(config)
            save_config(config)
            console.print(f"[green]✓[/green] Config refreshed at {config_path} (existing values preserved)")
    else:
        config = Config()
        _apply_recommended_tool_defaults(config)
        save_config(config)
        console.print(f"[green]✓[/green] Created config at {config_path}")
    
    # Create workspace
    workspace = get_workspace_path()
    get_env_dir()
    get_env_file().touch(exist_ok=True)
    get_mcp_home()
    get_global_skills_path()
    
    if not workspace.exists():
        workspace.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] Created workspace at {workspace}")
    
    # Create default bootstrap files
    _create_workspace_templates(workspace)
    
    console.print(f"\n{__logo__} nanobot is ready!")
    console.print("\nNext steps:")
    console.print("  1. Add your API key to [cyan]~/.nanobot/config.json[/cyan]")
    console.print("     Get one at: https://openrouter.ai/keys")
    console.print("  2. (Recommended) Put secrets in [cyan]~/.nanobot/.env[/cyan] or [cyan]~/.nanobot/env/*.env[/cyan]")
    console.print("     Use ${ENV_VAR} placeholders in config.json (apiBase/apiKey/etc.)")
    console.print("  3. Optional: install [cyan]uv[/cyan] to enable document parser MCP ([cyan]uvx[/cyan])")
    console.print("     Example: [cyan]brew install uv[/cyan]")
    console.print("  4. Chat: [cyan]nanobot agent -m \"Hello!\"[/cyan]")
    console.print("\n[dim]Runtime folders: ~/.nanobot/config.json, ~/.nanobot/.env, ~/.nanobot/env/, ~/.nanobot/mcp/, ~/.nanobot/skills/[/dim]")
    console.print("[dim]Default config now includes Exa MCP search and a docloader MCP template.[/dim]")
    console.print("[dim]Want Telegram/WhatsApp? See: https://github.com/HKUDS/nanobot#-chat-apps[/dim]")




def _create_workspace_templates(workspace: Path):
    """Create default workspace template files from bundled templates."""
    from importlib.resources import files as pkg_files

    templates_dir = pkg_files("nanobot") / "templates"
    for item in templates_dir.iterdir():
        if item.name == "memory" or not item.name.endswith(".md"):
            continue
        dest = workspace / item.name
        if not dest.exists():
            dest.write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
            console.print(f"  [dim]Created {item.name}[/dim]")

    # Create memory directory and MEMORY.md
    memory_dir = workspace / "memory"
    memory_dir.mkdir(exist_ok=True)
    memory_template = templates_dir / "memory" / "MEMORY.md"
    memory_file = memory_dir / "MEMORY.md"
    if not memory_file.exists():
        memory_file.write_text(memory_template.read_text(encoding="utf-8"), encoding="utf-8")
        console.print("  [dim]Created memory/MEMORY.md[/dim]")
    
    history_file = memory_dir / "HISTORY.md"
    if not history_file.exists():
        history_file.write_text("", encoding="utf-8")
        console.print("  [dim]Created memory/HISTORY.md[/dim]")

    # Create skills directory for custom user skills
    skills_dir = workspace / "skills"
    skills_dir.mkdir(exist_ok=True)


def _bootstrap_runtime_for_webui(config_path: Path | None = None) -> None:
    """Ensure config/workspace/runtime folders exist before starting the Web UI."""
    from nanobot.config.loader import get_config_path, load_config, save_config
    from nanobot.config.schema import Config
    from nanobot.utils.helpers import (
        get_env_dir,
        get_env_file,
        get_global_skills_path,
        get_mcp_home,
        get_workspace_path,
    )

    cfg_path = (config_path or get_config_path()).expanduser()

    if cfg_path.exists():
        config = load_config(cfg_path, apply_profiles=False, resolve_env=False)
        changed = False
        before = config.model_dump(by_alias=True)
        _apply_recommended_tool_defaults(config)
        after = config.model_dump(by_alias=True)
        changed = before != after
        if changed:
            save_config(config, cfg_path)
    else:
        config = Config()
        _apply_recommended_tool_defaults(config)
        save_config(config, cfg_path)
        console.print(f"[green]✓[/green] WebUI bootstrap created config at {cfg_path}")

    # Ensure runtime folders exist even if Web UI is used before onboard.
    get_env_dir()
    get_env_file().touch(exist_ok=True)
    get_mcp_home()
    get_global_skills_path()

    # Ensure workspace + templates exist for the main bot experience.
    workspace = config.workspace_path if getattr(config, "workspace_path", None) else get_workspace_path()
    workspace.mkdir(parents=True, exist_ok=True)
    _create_workspace_templates(workspace)


def _make_single_provider(config: Config, model: str):
    """Create a provider for a concrete model (non-endpoint-routed path)."""
    from nanobot.providers.litellm_provider import LiteLLMProvider
    from nanobot.providers.openai_codex_provider import OpenAICodexProvider
    from nanobot.providers.custom_provider import CustomProvider

    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    # OpenAI Codex (OAuth)
    if provider_name == "openai_codex" or model.startswith("openai-codex/"):
        return OpenAICodexProvider(default_model=model)

    # Custom: direct OpenAI-compatible endpoint, bypasses LiteLLM
    if provider_name == "custom":
        return CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
        )

    from nanobot.providers.registry import find_by_name
    spec = find_by_name(provider_name)
    if not model.startswith("bedrock/") and not (p and p.api_key) and not (spec and spec.is_oauth):
        console.print("[red]Error: No API key configured.[/red]")
        console.print("Set one in ~/.nanobot/config.json under providers section")
        raise typer.Exit(1)

    return LiteLLMProvider(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=provider_name,
    )


def _make_provider(config: Config):
    """Create the appropriate LLM provider from config."""
    model = config.agents.defaults.model

    if config.providers.endpoints:
        from nanobot.providers.router_provider import RouterProvider

        return RouterProvider(
            default_model=model,
            endpoints=config.providers.endpoints,
            fallback_factory=lambda fallback_model: _make_single_provider(config, fallback_model),
        )

    return _make_single_provider(config, model)


# ============================================================================
# Gateway / Server
# ============================================================================


@app.command()
def gateway(
    port: int = typer.Option(18790, "--port", "-p", help="Gateway port"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Start the nanobot gateway."""
    from nanobot.config.loader import load_config, get_data_dir
    from nanobot.bus.queue import MessageBus
    from nanobot.agent.loop import AgentLoop
    from nanobot.channels.manager import ChannelManager
    from nanobot.session.manager import SessionManager
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronJob
    from nanobot.heartbeat.service import HeartbeatService
    
    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    console.print(f"{__logo__} Starting nanobot gateway on port {port}...")
    
    config = load_config()
    _ensure_claude_code_runtime_dependencies(config)
    bus = MessageBus()
    provider = _make_provider(config)
    session_manager = SessionManager(config.workspace_path)
    
    # Create cron service first (callback set after agent creation)
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)
    
    # Create agent with cron service
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        exec_config=config.tools.exec,
        claude_code_config=config.tools.claude_code,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        session_manager=session_manager,
        mcp_servers=config.tools.mcp_servers,
        web_search_provider=config.tools.web.search.provider,
        mcp_enabled_servers=config.tools.mcp_enabled_servers,
        mcp_disabled_servers=config.tools.mcp_disabled_servers,
        mcp_enabled_tools=config.tools.mcp_enabled_tools,
        mcp_disabled_tools=config.tools.mcp_disabled_tools,
        tool_aliases=config.tools.aliases,
        enabled_tools=config.tools.enabled,
        disabled_skills=config.skills.disabled,
    )
    
    # Set cron callback (needs agent)
    async def on_cron_job(job: CronJob) -> str | None:
        """Execute a cron job through the agent."""
        response = await agent.process_direct(
            job.payload.message,
            session_key=f"cron:{job.id}",
            channel=job.payload.channel or "cli",
            chat_id=job.payload.to or "direct",
        )
        if job.payload.deliver and job.payload.to:
            from nanobot.bus.events import OutboundMessage
            await bus.publish_outbound(OutboundMessage(
                channel=job.payload.channel or "cli",
                chat_id=job.payload.to,
                content=response or ""
            ))
        return response
    cron.on_job = on_cron_job
    
    # Create heartbeat service
    async def on_heartbeat(prompt: str) -> str:
        """Execute heartbeat through the agent."""
        return await agent.process_direct(prompt, session_key="heartbeat")
    
    heartbeat = HeartbeatService(
        workspace=config.workspace_path,
        on_heartbeat=on_heartbeat,
        interval_s=30 * 60,  # 30 minutes
        enabled=True
    )
    
    # Create channel manager
    channels = ChannelManager(config, bus)
    
    if channels.enabled_channels:
        console.print(f"[green]✓[/green] Channels enabled: {', '.join(channels.enabled_channels)}")
    else:
        console.print("[yellow]Warning: No channels enabled[/yellow]")
    
    cron_status = cron.status()
    if cron_status["jobs"] > 0:
        console.print(f"[green]✓[/green] Cron: {cron_status['jobs']} scheduled jobs")
    
    console.print(f"[green]✓[/green] Heartbeat: every 30m")
    
    async def run():
        try:
            await cron.start()
            await heartbeat.start()
            await asyncio.gather(
                agent.run(),
                channels.start_all(),
            )
        except KeyboardInterrupt:
            console.print("\nShutting down...")
        finally:
            await agent.close_mcp()
            heartbeat.stop()
            cron.stop()
            agent.stop()
            await channels.stop_all()
    
    asyncio.run(run())




# ============================================================================
# Agent Commands
# ============================================================================


@app.command()
def agent(
    message: str = typer.Option(None, "--message", "-m", help="Message to send to the agent"),
    session_id: str = typer.Option("cli:direct", "--session", "-s", help="Session ID"),
    markdown: bool = typer.Option(True, "--markdown/--no-markdown", help="Render assistant output as Markdown"),
    logs: bool = typer.Option(False, "--logs/--no-logs", help="Show nanobot runtime logs during chat"),
):
    """Interact with the agent directly."""
    from nanobot.config.loader import load_config, get_data_dir
    from nanobot.bus.queue import MessageBus
    from nanobot.agent.loop import AgentLoop
    from nanobot.cron.service import CronService
    from loguru import logger
    
    config = load_config()
    _ensure_claude_code_runtime_dependencies(config)
    
    bus = MessageBus()
    provider = _make_provider(config)

    # Create cron service for tool usage (no callback needed for CLI unless running)
    cron_store_path = get_data_dir() / "cron" / "jobs.json"
    cron = CronService(cron_store_path)

    if logs:
        logger.enable("nanobot")
    else:
        logger.disable("nanobot")
    
    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        exec_config=config.tools.exec,
        claude_code_config=config.tools.claude_code,
        cron_service=cron,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        web_search_provider=config.tools.web.search.provider,
        mcp_enabled_servers=config.tools.mcp_enabled_servers,
        mcp_disabled_servers=config.tools.mcp_disabled_servers,
        mcp_enabled_tools=config.tools.mcp_enabled_tools,
        mcp_disabled_tools=config.tools.mcp_disabled_tools,
        tool_aliases=config.tools.aliases,
        enabled_tools=config.tools.enabled,
        disabled_skills=config.skills.disabled,
    )
    
    # Show spinner when logs are off (no output to miss); skip when logs are on
    def _thinking_ctx():
        if logs:
            from contextlib import nullcontext
            return nullcontext()
        # Animated spinner is safe to use with prompt_toolkit input handling
        return console.status("[dim]nanobot is thinking...[/dim]", spinner="dots")

    async def _cli_progress(content: str) -> None:
        console.print(f"  [dim]↳ {content}[/dim]")

    if message:
        # Single message mode — direct call, no bus needed
        async def run_once():
            with _thinking_ctx():
                response = await agent_loop.process_direct(message, session_id, on_progress=_cli_progress)
            _print_agent_response(response, render_markdown=markdown)
            await agent_loop.close_mcp()

        asyncio.run(run_once())
    else:
        # Interactive mode — route through bus like other channels
        from nanobot.bus.events import InboundMessage
        _init_prompt_session()
        console.print(f"{__logo__} Interactive mode (type [bold]exit[/bold] or [bold]Ctrl+C[/bold] to quit)\n")

        if ":" in session_id:
            cli_channel, cli_chat_id = session_id.split(":", 1)
        else:
            cli_channel, cli_chat_id = "cli", session_id

        def _exit_on_sigint(signum, frame):
            _restore_terminal()
            console.print("\nGoodbye!")
            os._exit(0)

        signal.signal(signal.SIGINT, _exit_on_sigint)

        async def run_interactive():
            bus_task = asyncio.create_task(agent_loop.run())
            turn_done = asyncio.Event()
            turn_done.set()
            turn_response: list[str] = []

            async def _consume_outbound():
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
                            _print_agent_response(msg.content, render_markdown=markdown)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

            outbound_task = asyncio.create_task(_consume_outbound())

            try:
                while True:
                    try:
                        _flush_pending_tty_input()
                        user_input = await _read_interactive_input_async()
                        command = user_input.strip()
                        if not command:
                            continue

                        if _is_exit_command(command):
                            _restore_terminal()
                            console.print("\nGoodbye!")
                            break

                        turn_done.clear()
                        turn_response.clear()

                        await bus.publish_inbound(InboundMessage(
                            channel=cli_channel,
                            sender_id="user",
                            chat_id=cli_chat_id,
                            content=user_input,
                        ))

                        with _thinking_ctx():
                            await turn_done.wait()

                        if turn_response:
                            _print_agent_response(turn_response[0], render_markdown=markdown)
                    except KeyboardInterrupt:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
                    except EOFError:
                        _restore_terminal()
                        console.print("\nGoodbye!")
                        break
            finally:
                agent_loop.stop()
                outbound_task.cancel()
                await asyncio.gather(bus_task, outbound_task, return_exceptions=True)
                await agent_loop.close_mcp()

        asyncio.run(run_interactive())


# ============================================================================
# Channel Commands
# ============================================================================


channels_app = typer.Typer(help="Manage channels")
app.add_typer(channels_app, name="channels")


@channels_app.command("status")
def channels_status():
    """Show channel status."""
    from nanobot.config.loader import load_config

    config = load_config()
    _ensure_claude_code_runtime_dependencies(config)

    table = Table(title="Channel Status")
    table.add_column("Channel", style="cyan")
    table.add_column("Enabled", style="green")
    table.add_column("Configuration", style="yellow")

    # WhatsApp
    wa = config.channels.whatsapp
    table.add_row(
        "WhatsApp",
        "✓" if wa.enabled else "✗",
        wa.bridge_url
    )

    dc = config.channels.discord
    table.add_row(
        "Discord",
        "✓" if dc.enabled else "✗",
        dc.gateway_url
    )

    # Feishu
    fs = config.channels.feishu
    fs_config = f"app_id: {fs.app_id[:10]}..." if fs.app_id else "[dim]not configured[/dim]"
    table.add_row(
        "Feishu",
        "✓" if fs.enabled else "✗",
        fs_config
    )

    # Mochat
    mc = config.channels.mochat
    mc_base = mc.base_url or "[dim]not configured[/dim]"
    table.add_row(
        "Mochat",
        "✓" if mc.enabled else "✗",
        mc_base
    )
    
    # Telegram
    tg = config.channels.telegram
    tg_config = f"token: {tg.token[:10]}..." if tg.token else "[dim]not configured[/dim]"
    table.add_row(
        "Telegram",
        "✓" if tg.enabled else "✗",
        tg_config
    )

    # Slack
    slack = config.channels.slack
    slack_config = "socket" if slack.app_token and slack.bot_token else "[dim]not configured[/dim]"
    table.add_row(
        "Slack",
        "✓" if slack.enabled else "✗",
        slack_config
    )

    # DingTalk
    dt = config.channels.dingtalk
    dt_config = f"client_id: {dt.client_id[:10]}..." if dt.client_id else "[dim]not configured[/dim]"
    table.add_row(
        "DingTalk",
        "✓" if dt.enabled else "✗",
        dt_config
    )

    # QQ
    qq = config.channels.qq
    qq_config = f"app_id: {qq.app_id[:10]}..." if qq.app_id else "[dim]not configured[/dim]"
    table.add_row(
        "QQ",
        "✓" if qq.enabled else "✗",
        qq_config
    )

    # Email
    em = config.channels.email
    em_config = em.imap_host if em.imap_host else "[dim]not configured[/dim]"
    table.add_row(
        "Email",
        "✓" if em.enabled else "✗",
        em_config
    )

    console.print(table)


def _get_bridge_dir() -> Path:
    """Get the bridge directory, setting it up if needed."""
    import shutil
    import subprocess
    
    # User's bridge location
    from nanobot.utils.helpers import get_bridge_dir
    user_bridge = get_bridge_dir()
    
    # Check if already built
    if (user_bridge / "dist" / "index.js").exists():
        return user_bridge
    
    # Check for npm
    if not shutil.which("npm"):
        console.print("[red]npm not found. Please install Node.js >= 18.[/red]")
        raise typer.Exit(1)
    
    # Find source bridge: first check package data, then source dir
    pkg_bridge = Path(__file__).parent.parent / "bridge"  # nanobot/bridge (installed)
    src_bridge = Path(__file__).parent.parent.parent / "bridge"  # repo root/bridge (dev)
    
    source = None
    if (pkg_bridge / "package.json").exists():
        source = pkg_bridge
    elif (src_bridge / "package.json").exists():
        source = src_bridge
    
    if not source:
        console.print("[red]Bridge source not found.[/red]")
        console.print("Try reinstalling: pip install --force-reinstall nanobot")
        raise typer.Exit(1)
    
    console.print(f"{__logo__} Setting up bridge...")
    
    # Copy to user directory
    user_bridge.parent.mkdir(parents=True, exist_ok=True)
    if user_bridge.exists():
        shutil.rmtree(user_bridge)
    shutil.copytree(source, user_bridge, ignore=shutil.ignore_patterns("node_modules", "dist"))
    
    # Install and build
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


@channels_app.command("login")
def channels_login():
    """Link device via QR code."""
    import subprocess
    from nanobot.config.loader import load_config
    
    config = load_config()
    bridge_dir = _get_bridge_dir()
    
    console.print(f"{__logo__} Starting bridge...")
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
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    jobs = service.list_jobs(include_disabled=all)
    
    if not jobs:
        console.print("No scheduled jobs.")
        return
    
    table = Table(title="Scheduled Jobs")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Schedule")
    table.add_column("Status")
    table.add_column("Next Run")
    
    import time
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    for job in jobs:
        # Format schedule
        if job.schedule.kind == "every":
            sched = f"every {(job.schedule.every_ms or 0) // 1000}s"
        elif job.schedule.kind == "cron":
            sched = f"{job.schedule.expr or ''} ({job.schedule.tz})" if job.schedule.tz else (job.schedule.expr or "")
        else:
            sched = "one-time"
        
        # Format next run
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
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronSchedule
    
    if tz and not cron_expr:
        console.print("[red]Error: --tz can only be used with --cron[/red]")
        raise typer.Exit(1)

    # Determine schedule type
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


@cron_app.command("remove")
def cron_remove(
    job_id: str = typer.Argument(..., help="Job ID to remove"),
):
    """Remove a scheduled job."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    if service.remove_job(job_id):
        console.print(f"[green]✓[/green] Removed job {job_id}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("enable")
def cron_enable(
    job_id: str = typer.Argument(..., help="Job ID"),
    disable: bool = typer.Option(False, "--disable", help="Disable instead of enable"),
):
    """Enable or disable a job."""
    from nanobot.config.loader import get_data_dir
    from nanobot.cron.service import CronService
    
    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)
    
    job = service.enable_job(job_id, enabled=not disable)
    if job:
        status = "disabled" if disable else "enabled"
        console.print(f"[green]✓[/green] Job '{job.name}' {status}")
    else:
        console.print(f"[red]Job {job_id} not found[/red]")


@cron_app.command("run")
def cron_run(
    job_id: str = typer.Argument(..., help="Job ID to run"),
    force: bool = typer.Option(False, "--force", "-f", help="Run even if disabled"),
):
    """Manually run a job."""
    from loguru import logger
    from nanobot.config.loader import load_config, get_data_dir
    from nanobot.cron.service import CronService
    from nanobot.cron.types import CronJob
    from nanobot.bus.queue import MessageBus
    from nanobot.agent.loop import AgentLoop
    logger.disable("nanobot")

    config = load_config()
    provider = _make_provider(config)
    bus = MessageBus()
    agent_loop = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=config.workspace_path,
        model=config.agents.defaults.model,
        temperature=config.agents.defaults.temperature,
        max_tokens=config.agents.defaults.max_tokens,
        max_iterations=config.agents.defaults.max_tool_iterations,
        memory_window=config.agents.defaults.memory_window,
        exec_config=config.tools.exec,
        claude_code_config=config.tools.claude_code,
        restrict_to_workspace=config.tools.restrict_to_workspace,
        mcp_servers=config.tools.mcp_servers,
        web_search_provider=config.tools.web.search.provider,
        mcp_enabled_servers=config.tools.mcp_enabled_servers,
        mcp_disabled_servers=config.tools.mcp_disabled_servers,
        mcp_enabled_tools=config.tools.mcp_enabled_tools,
        mcp_disabled_tools=config.tools.mcp_disabled_tools,
        tool_aliases=config.tools.aliases,
        enabled_tools=config.tools.enabled,
        disabled_skills=config.skills.disabled,
    )

    store_path = get_data_dir() / "cron" / "jobs.json"
    service = CronService(store_path)

    result_holder = []

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
            _print_agent_response(result_holder[0], render_markdown=True)
    else:
        console.print(f"[red]Failed to run job {job_id}[/red]")


# ============================================================================
# Status Commands
# ============================================================================


@app.command()
def status():
    """Show nanobot status."""
    from nanobot.config.loader import load_config, get_config_path, _discover_env_files
    from nanobot.utils.helpers import get_mcp_home, get_global_skills_path, get_env_dir, get_env_file
    from nanobot.agent.skills import SkillsLoader
    from nanobot.agent.tools.web import has_exa_search_mcp

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} nanobot Status\n")

    console.print(f"Config: {config_path} {'[green]✓[/green]' if config_path.exists() else '[red]✗[/red]'}")
    console.print(f"Workspace: {workspace} {'[green]✓[/green]' if workspace.exists() else '[red]✗[/red]'}")
    console.print(f"Global skills dir: {get_global_skills_path()} {'[green]✓[/green]' if get_global_skills_path().exists() else '[red]✗[/red]'}")
    console.print(f"MCP home: {get_mcp_home()} {'[green]✓[/green]' if get_mcp_home().exists() else '[red]✗[/red]'}")
    console.print(f"Env file: {get_env_file()} {'[green]✓[/green]' if get_env_file().exists() else '[dim](not created)[/dim]'}")
    console.print(f"Env dir: {get_env_dir()} {'[green]✓[/green]' if get_env_dir().exists() else '[red]✗[/red]'}")
    env_files = _discover_env_files()
    if env_files:
        console.print(f"Env files: {len(env_files)} loaded helper file(s)")

    if config_path.exists():
        from nanobot.providers.registry import PROVIDERS

        console.print(f"Model: {config.agents.defaults.model}")
        
        # Check API keys from registry
        for spec in PROVIDERS:
            p = getattr(config.providers, spec.name, None)
            if p is None:
                continue
            if spec.is_oauth:
                console.print(f"{spec.label}: [green]✓ (OAuth)[/green]")
            elif spec.is_local:
                # Local deployments show api_base instead of api_key
                if p.api_base:
                    console.print(f"{spec.label}: [green]✓ {p.api_base}[/green]")
                else:
                    console.print(f"{spec.label}: [dim]not set[/dim]")
            else:
                has_key = bool(p.api_key)
                console.print(f"{spec.label}: {'[green]✓[/green]' if has_key else '[dim]not set[/dim]'}")

        if config.providers.endpoints:
            console.print(f"Named endpoints: {len(config.providers.endpoints)} configured")
            for name, ep in config.providers.endpoints.items():
                enabled = bool(getattr(ep, "enabled", True))
                models_count = len(ep.models or [])
                tag = "[green]enabled[/green]" if enabled else "[dim]disabled[/dim]"
                console.print(f"  - {name}: {tag} type={ep.type} models={models_count if models_count else '*'}")

        console.print("\n[bold]Tool & Skill Diagnostics[/bold]")
        active_profile = (config.profiles.active or "").strip()
        if active_profile:
            profile_ok = active_profile in config.profiles.items
            console.print(
                f"Profile: {active_profile} "
                f"{'[green]✓[/green]' if profile_ok else '[red](missing definition)[/red]'} "
                f"({len(config.profiles.items)} defined)"
            )
        elif config.profiles.items:
            console.print(f"Profile: [dim]none active[/dim] ({len(config.profiles.items)} defined)")

        builtins = config.tools.enabled or ["(all built-in tools enabled)"]
        console.print(f"Built-in tools: {', '.join(builtins)}")
        ccfg = config.tools.claude_code
        cc_tool_enabled = bool(ccfg.enabled)
        cc_tool_whitelisted = (not config.tools.enabled) or ("claude_code" in {t.lower() for t in config.tools.enabled})
        cc_tmux_ok = shutil.which(ccfg.tmux_command) is not None
        cc_cmd_ok = shutil.which(ccfg.command) is not None if "/" not in ccfg.command else Path(ccfg.command).expanduser().exists()
        console.print(
            "Claude Code tool: "
            f"{'[green]enabled[/green]' if cc_tool_enabled else '[dim]disabled[/dim]'}"
            f", whitelist={'yes' if cc_tool_whitelisted else 'no'}"
            f", tmux={'ok' if cc_tmux_ok else 'missing'}"
            f", claude={'ok' if cc_cmd_ok else 'missing'}"
        )
        if cc_tool_enabled:
            console.print(f"  autoInstallTmux: {'on' if ccfg.auto_install_tmux else 'off'}")
        if config.tools.aliases:
            console.print(f"Tool aliases: {len(config.tools.aliases)} configured")
            for alias_name, target_name in config.tools.aliases.items():
                if not str(alias_name).strip() or not str(target_name).strip():
                    console.print(f"  - {alias_name} -> {target_name}: [red]invalid[/red]")
                    continue
                if str(alias_name).strip() == str(target_name).strip():
                    console.print(f"  - {alias_name} -> {target_name}: [yellow]noop alias[/yellow]")
                    continue
                console.print(f"  - {alias_name} -> {target_name}")
        else:
            console.print("Tool aliases: [dim]none[/dim]")

        disabled_skills = config.skills.disabled or []
        console.print(
            f"Disabled skills: {', '.join(disabled_skills) if disabled_skills else '[dim]none[/dim]'}"
        )
        skill_loader = SkillsLoader(workspace, disabled_skills=set(disabled_skills))
        skill_report = skill_loader.build_availability_report()
        unavailable_skills = [s for s in skill_report if not bool(s["available"])]
        if skill_report:
            console.print(
                f"Skill availability: {len(skill_report) - len(unavailable_skills)}/{len(skill_report)} ready"
            )
            if unavailable_skills[:5]:
                for s in unavailable_skills[:5]:
                    reason = s.get("requires") or "requirements missing"
                    console.print(f"  - {s['name']}: [dim]{reason}[/dim]")
                if len(unavailable_skills) > 5:
                    console.print(f"  [dim]... {len(unavailable_skills) - 5} more unavailable skills[/dim]")

        provider_mode = (config.tools.web.search.provider or "exa_mcp").strip().lower()
        if provider_mode not in {"exa_mcp", "disabled"}:
            provider_mode = "exa_mcp"
        enabled_servers = {s.lower() for s in config.tools.mcp_enabled_servers}
        disabled_servers = {s.lower() for s in config.tools.mcp_disabled_servers}
        configured_servers = list(config.tools.mcp_servers.keys())
        active_mcp_servers: dict[str, object] = {}
        for name in configured_servers:
            lname = name.lower()
            if enabled_servers and lname not in enabled_servers:
                continue
            if lname in disabled_servers:
                continue
            active_mcp_servers[name] = config.tools.mcp_servers[name]

        enabled_mcp_tools = {s.lower() for s in config.tools.mcp_enabled_tools}
        disabled_mcp_tools = {s.lower() for s in config.tools.mcp_disabled_tools}

        def _mcp_tool_filter_allows(server_name: str, tool_name: str) -> bool:
            aliases = {
                tool_name.lower(),
                f"mcp_{server_name}_{tool_name}".lower(),
                f"{server_name}.{tool_name}".lower(),
            }
            if enabled_mcp_tools and not (aliases & enabled_mcp_tools):
                return False
            if disabled_mcp_tools and (aliases & disabled_mcp_tools):
                return False
            return True

        active_exa_servers = [
            name for name, cfg in active_mcp_servers.items()
            if has_exa_search_mcp({name: cfg})
        ]
        exa_configured = bool(active_exa_servers)
        exa_web_search_exposed = any(
            _mcp_tool_filter_allows(name, "web_search_exa") for name in active_exa_servers
        )

        if provider_mode == "disabled":
            effective_search = "disabled"
        elif provider_mode == "exa_mcp":
            if exa_configured and exa_web_search_exposed:
                effective_search = "exa_mcp"
            elif exa_configured:
                effective_search = "exa_mcp (web_search_exa filtered out)"
            else:
                effective_search = "exa_mcp (missing exa mcp server config)"
        else:
            effective_search = "unknown"
        console.print(f"Web search provider: {provider_mode}  ->  {effective_search}")

        active_servers: list[str] = []
        for name in configured_servers:
            lname = name.lower()
            if enabled_servers and lname not in enabled_servers:
                continue
            if lname in disabled_servers:
                continue
            active_servers.append(name)
        console.print(
            f"MCP servers: {len(configured_servers)} configured, {len(active_servers)} active after filters"
        )
        if config.tools.mcp_enabled_tools or config.tools.mcp_disabled_tools:
            console.print(
                "MCP tool filters: "
                f"allow={len(config.tools.mcp_enabled_tools)} deny={len(config.tools.mcp_disabled_tools)}"
            )

        for name in configured_servers:
            cfg = config.tools.mcp_servers[name]
            lname = name.lower()
            if enabled_servers and lname not in enabled_servers:
                console.print(f"  - {name}: [dim]disabled by tools.mcpEnabledServers[/dim]")
                continue
            if lname in disabled_servers:
                console.print(f"  - {name}: [dim]disabled by tools.mcpDisabledServers[/dim]")
                continue
            if cfg.url:
                console.print(f"  - {name}: [green]remote[/green] {cfg.url}")
                continue
            if cfg.command:
                cmd_ok = shutil.which(cfg.command) is not None
                status_text = "[green]ready[/green]" if cmd_ok else "[red]missing command[/red]"
                console.print(f"  - {name}: {status_text} `{cfg.command}`")
                continue
            console.print(f"  - {name}: [red]invalid config[/red] (missing command/url)")

        warnings: list[str] = []
        if provider_mode == "exa_mcp" and not exa_configured:
            warnings.append("web_search provider=exa_mcp but Exa MCP server is not configured")
        if provider_mode == "exa_mcp" and exa_configured and not exa_web_search_exposed:
            warnings.append("Exa MCP is active but web_search_exa is filtered by MCP tool filters")
        if config.tools.enabled and "web_search" not in {t.lower() for t in config.tools.enabled}:
            warnings.append("web_search is excluded by tools.enabled")
        for alias_name, target_name in config.tools.aliases.items():
            if not str(alias_name).strip() or not str(target_name).strip():
                warnings.append(f"invalid tool alias entry: {alias_name!r} -> {target_name!r}")
            elif str(alias_name).strip() == str(target_name).strip():
                warnings.append(f"noop tool alias: {alias_name} -> {target_name}")
        if warnings:
            console.print("[yellow]Warnings:[/yellow]")
            for item in warnings:
                console.print(f"  - {item}")


@app.command()
def doctor():
    """Diagnose configuration/tooling issues and suggest fixes."""
    from nanobot.config.loader import load_config, get_config_path, _discover_env_files
    from nanobot.utils.helpers import get_mcp_home, get_global_skills_path, get_env_file, get_env_dir
    from nanobot.agent.skills import SkillsLoader

    config_path = get_config_path()
    config = load_config()
    workspace = config.workspace_path

    console.print(f"{__logo__} nanobot Doctor\n")
    console.print("[bold]Summary[/bold]")
    console.print(f"- Config path: {config_path} ({'exists' if config_path.exists() else 'missing'})")
    console.print(f"- Workspace: {workspace} ({'exists' if workspace.exists() else 'missing'})")
    console.print(f"- Active profile: {config.profiles.active or 'none'}")
    console.print(f"- Global skills dir: {get_global_skills_path()}")
    console.print(f"- MCP home: {get_mcp_home()}")
    console.print(f"- Env file: {get_env_file()} ({'exists' if get_env_file().exists() else 'missing'})")
    console.print(f"- Env dir: {get_env_dir()} ({'exists' if get_env_dir().exists() else 'missing'})")
    env_files = _discover_env_files()
    console.print(f"- Env helper files: {len(env_files)}")

    findings: list[tuple[str, str, str]] = []  # severity, problem, fix

    active_profile = (config.profiles.active or "").strip()
    if active_profile and active_profile not in config.profiles.items:
        findings.append((
            "warn",
            f"profiles.active='{active_profile}' but no matching definition in profiles.items",
            "Add profiles.items.<name> or clear profiles.active to disable profile overlay.",
        ))

    provider_mode = (config.tools.web.search.provider or "exa_mcp").strip().lower()
    if provider_mode not in {"exa_mcp", "disabled"}:
        provider_mode = "exa_mcp"
    exa_cfg = config.tools.mcp_servers.get("exa")
    if provider_mode == "exa_mcp" and not exa_cfg:
        findings.append((
            "error",
            "web search provider is exa_mcp but MCP server 'exa' is not configured",
            "Add tools.mcpServers.exa.url = https://mcp.exa.ai/mcp?tools=web_search_exa,get_code_context_exa",
        ))

    ccfg = config.tools.claude_code
    tool_enabled_names = {t.lower() for t in (config.tools.enabled or [])}
    if ccfg.enabled and tool_enabled_names and "claude_code" not in tool_enabled_names:
        findings.append((
            "warn",
            "tools.claudeCode.enabled=true but `claude_code` is excluded by tools.enabled",
            "Add `claude_code` to tools.enabled or clear tools.enabled to allow all built-in tools.",
        ))
    if ccfg.enabled and shutil.which(ccfg.tmux_command) is None:
        findings.append((
            "error",
            f"Claude Code tool is enabled but tmux command '{ccfg.tmux_command}' is not found",
            (
                "tmux will be auto-installed on startup if tools.claudeCode.autoInstallTmux=true; "
                "otherwise install it manually (e.g. `brew install tmux`) or set tools.claudeCode.tmuxCommand correctly."
            ),
        ))
    if ccfg.enabled:
        claude_exists = shutil.which(ccfg.command) is not None if "/" not in ccfg.command else Path(ccfg.command).expanduser().exists()
        if not claude_exists:
            findings.append((
                "error",
                f"Claude Code tool is enabled but command '{ccfg.command}' is not found",
                "Install Claude Code CLI or set tools.claudeCode.command to the executable path.",
            ))

    doc_cfg = config.tools.mcp_servers.get("docloader")
    if doc_cfg:
        if doc_cfg.command and shutil.which(doc_cfg.command) is None:
            findings.append((
                "error",
                f"docloader MCP command '{doc_cfg.command}' not found",
                "Install uv (e.g. `brew install uv`) so `uvx` can launch the document loader MCP.",
            ))
    else:
        findings.append((
            "warn",
            "document parsing MCP is not configured (PDF/Word/PPT/Excel/image parsing will rely on limited built-ins)",
            "Add tools.mcpServers.docloader (uvx awslabs.document-loader-mcp-server@latest) and aliases doc_read/image_read.",
        ))

    if config.tools.aliases:
        for alias_name, target_name in config.tools.aliases.items():
            a = str(alias_name).strip()
            t = str(target_name).strip()
            if not a or not t:
                findings.append(("warn", f"invalid tool alias entry: {alias_name!r} -> {target_name!r}", "Remove empty alias keys/values."))
            elif a == t:
                findings.append(("warn", f"noop tool alias: {a} -> {t}", "Delete the alias or point it to a different target tool."))

    active_model = str(config.agents.defaults.model or "")
    if "/" in active_model:
        ep_name, ep_model = active_model.split("/", 1)
        ep_cfg = config.providers.endpoints.get(ep_name)
        if ep_cfg:
            etype = str(ep_cfg.type or "").strip().lower()
            supported = {
                "openai_compatible", "anthropic", "openai", "openrouter", "deepseek", "groq",
                "zhipu", "dashscope", "vllm", "gemini", "moonshot", "minimax",
                "aihubmix", "siliconflow", "volcengine",
            }
            if not ep_cfg.enabled:
                findings.append((
                    "error",
                    f"default model points to disabled endpoint '{ep_name}'",
                    f"Enable providers.endpoints.{ep_name}.enabled or switch agents.defaults.model to another endpoint/model.",
                ))
            if etype.replace("-", "_") not in supported:
                findings.append((
                    "error",
                    f"endpoint '{ep_name}' uses unsupported type '{ep_cfg.type}'",
                    "Use openai_compatible or a supported provider type (anthropic/openrouter/openai/... ).",
                ))
            if ep_cfg.models and ep_model not in set(ep_cfg.models):
                findings.append((
                    "warn",
                    f"default model '{active_model}' is not listed in providers.endpoints.{ep_name}.models",
                    "Add the model to the endpoint's models list or clear the list to allow any model.",
                ))
            if etype.replace("-", "_") == "openai_compatible" and not ep_cfg.api_base:
                findings.append((
                    "warn",
                    f"endpoint '{ep_name}' is openai_compatible but apiBase is empty",
                    f"Set providers.endpoints.{ep_name}.apiBase to your OpenAI-compatible endpoint.",
                ))
            if ep_cfg.api_key and "${" in str(ep_cfg.api_key):
                findings.append((
                    "warn",
                    f"providers.endpoints.{ep_name}.apiKey contains an unresolved ${'{'}ENV_VAR{'}'} placeholder",
                    "Check ~/.nanobot/.env or ~/.nanobot/env/*.env and ensure the referenced variable exists.",
                ))

    if active_model.startswith("custom/") and "custom" not in config.providers.endpoints:
        if not config.providers.custom.api_base:
            findings.append((
                "warn",
                "default model uses custom/* but providers.custom.apiBase is empty",
                "Set providers.custom.apiBase to your OpenAI-compatible endpoint.",
            ))
        if not config.providers.custom.api_key:
            findings.append((
                "warn",
                "default model uses custom/* but providers.custom.apiKey is empty (or env placeholder not resolved)",
                "Set providers.custom.apiKey or use ${ENV_VAR} with a helper env file under ~/.nanobot/.env or ~/.nanobot/env/*.env.",
            ))
        elif "${" in str(config.providers.custom.api_key):
            findings.append((
                "warn",
                "providers.custom.apiKey still contains an unresolved ${ENV_VAR} placeholder",
                "Check ~/.nanobot/.env or ~/.nanobot/env/*.env and ensure the referenced variable name exists.",
            ))
        if config.providers.custom.api_base and "${" in str(config.providers.custom.api_base):
            findings.append((
                "warn",
                "providers.custom.apiBase still contains an unresolved ${ENV_VAR} placeholder",
                "Check your helper env files and variable names for MY_API_BASE-like values.",
            ))

    # Skills availability diagnosis (respects explicit disabled list).
    disabled_skills = set(config.skills.disabled or [])
    loader = SkillsLoader(workspace, disabled_skills=disabled_skills)
    for row in loader.build_availability_report():
        if bool(row["available"]):
            continue
        reason = str(row.get("requires") or "requirements missing")
        fix = "Install the missing CLI/env requirement or add the skill to skills.disabled."
        if "CLI: gh" in reason:
            fix = "Install GitHub CLI (`brew install gh`) and run `gh auth login`, or disable the github skill."
        elif "CLI: uvx" in reason or "CLI: uv" in reason:
            fix = "Install uv (`brew install uv`) to enable document/tool MCP skills."
        findings.append(("warn", f"skill '{row['name']}' unavailable: {reason}", fix))

    console.print("\n[bold]Findings[/bold]")
    if not findings:
        console.print("[green]No blocking issues found.[/green]")
    else:
        for severity, problem, fix in findings:
            color = "red" if severity == "error" else "yellow"
            console.print(f"- [{color}]{severity.upper()}[/{color}] {problem}")
            console.print(f"  Fix: {fix}")

    console.print("\n[bold]Recommended next actions[/bold]")
    console.print("1. Run `nanobot onboard` to refresh config and workspace templates with current defaults.")
    console.print("2. Keep `profiles.active=cn_dev` for lightweight local use; switch to `research` when you need more tools.")
    console.print("3. Test attachments with `doc_read` / `image_read` after enabling docloader MCP.")


@app.command()
def webui(
    host: str = typer.Option("127.0.0.1", help="Bind host (default localhost for safety)"),
    port: int = typer.Option(18791, help="Bind port for the local web UI"),
    config_path: Path | None = typer.Option(None, "--config", help="Optional config file path"),
    open_browser: bool = typer.Option(False, help="Open browser automatically after startup"),
    token: str | None = typer.Option(
        None,
        "--token",
        help="Optional Web UI auth token (HTTP Basic password). Can also use NANOBOT_WEBUI_TOKEN.",
        envvar="NANOBOT_WEBUI_TOKEN",
    ),
):
    """Run a lightweight local web UI for config / MCP / skills / channels management."""
    from nanobot.webui.server import run_webui

    _bootstrap_runtime_for_webui(config_path)
    run_webui(host=host, port=port, config_path=config_path, open_browser=open_browser, auth_token=token)


# ============================================================================
# OAuth Login
# ============================================================================

provider_app = typer.Typer(help="Manage providers")
app.add_typer(provider_app, name="provider")


_LOGIN_HANDLERS: dict[str, callable] = {}


def _register_login(name: str):
    def decorator(fn):
        _LOGIN_HANDLERS[name] = fn
        return fn
    return decorator


@provider_app.command("login")
def provider_login(
    provider: str = typer.Argument(..., help="OAuth provider (e.g. 'openai-codex', 'github-copilot')"),
):
    """Authenticate with an OAuth provider."""
    from nanobot.providers.registry import PROVIDERS

    key = provider.replace("-", "_")
    spec = next((s for s in PROVIDERS if s.name == key and s.is_oauth), None)
    if not spec:
        names = ", ".join(s.name.replace("_", "-") for s in PROVIDERS if s.is_oauth)
        console.print(f"[red]Unknown OAuth provider: {provider}[/red]  Supported: {names}")
        raise typer.Exit(1)

    handler = _LOGIN_HANDLERS.get(spec.name)
    if not handler:
        console.print(f"[red]Login not implemented for {spec.label}[/red]")
        raise typer.Exit(1)

    console.print(f"{__logo__} OAuth Login - {spec.label}\n")
    handler()


@_register_login("openai_codex")
def _login_openai_codex() -> None:
    try:
        from oauth_cli_kit import get_token, login_oauth_interactive
        token = None
        try:
            token = get_token()
        except Exception:
            pass
        if not (token and token.access):
            console.print("[cyan]Starting interactive OAuth login...[/cyan]\n")
            token = login_oauth_interactive(
                print_fn=lambda s: console.print(s),
                prompt_fn=lambda s: typer.prompt(s),
            )
        if not (token and token.access):
            console.print("[red]✗ Authentication failed[/red]")
            raise typer.Exit(1)
        console.print(f"[green]✓ Authenticated with OpenAI Codex[/green]  [dim]{token.account_id}[/dim]")
    except ImportError:
        console.print("[red]oauth_cli_kit not installed. Run: pip install oauth-cli-kit[/red]")
        raise typer.Exit(1)


@_register_login("github_copilot")
def _login_github_copilot() -> None:
    import asyncio

    console.print("[cyan]Starting GitHub Copilot device flow...[/cyan]\n")

    async def _trigger():
        from litellm import acompletion
        await acompletion(model="github_copilot/gpt-4o", messages=[{"role": "user", "content": "hi"}], max_tokens=1)

    try:
        asyncio.run(_trigger())
        console.print("[green]✓ Authenticated with GitHub Copilot[/green]")
    except Exception as e:
        console.print(f"[red]Authentication error: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
