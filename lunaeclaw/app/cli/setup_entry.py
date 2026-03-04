"""Setup and bootstrap command handlers for CLI/WebUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import typer

from lunaeclaw.platform.config.schema import Config


def create_workspace_templates(workspace: Path, *, console: Any) -> None:
    """Create default workspace template files from bundled templates."""
    from importlib.resources import files as pkg_files

    templates_dir = pkg_files("lunaeclaw") / "templates"
    for item in templates_dir.iterdir():
        if item.name == "memory" or not item.name.endswith(".md"):
            continue
        dest = workspace / item.name
        if not dest.exists():
            dest.write_text(item.read_text(encoding="utf-8"), encoding="utf-8")
            console.print(f"  [dim]Created {item.name}[/dim]")

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

    skills_dir = workspace / "skills"
    skills_dir.mkdir(exist_ok=True)


def bootstrap_runtime_for_webui(
    config_path: Path | None = None,
    *,
    console: Any,
    apply_recommended_tool_defaults: Callable[[Config], None],
) -> None:
    """Ensure config/workspace/runtime folders exist before starting the Web UI."""
    from lunaeclaw.platform.config.loader import get_config_path, load_config, save_config
    from lunaeclaw.platform.utils.helpers import (
        get_env_dir,
        get_env_file,
        get_global_skills_path,
        get_mcp_home,
        get_workspace_path,
    )

    cfg_path = (config_path or get_config_path()).expanduser()

    if cfg_path.exists():
        config = load_config(cfg_path, apply_profiles=False, resolve_env=False)
        before = config.model_dump(by_alias=True)
        apply_recommended_tool_defaults(config)
        after = config.model_dump(by_alias=True)
        if before != after:
            save_config(config, cfg_path)
    else:
        config = Config()
        apply_recommended_tool_defaults(config)
        save_config(config, cfg_path)
        console.print(f"[green]✓[/green] WebUI bootstrap created config at {cfg_path}")

    get_env_dir()
    get_env_file().touch(exist_ok=True)
    get_mcp_home()
    get_global_skills_path()

    workspace = config.workspace_path if getattr(config, "workspace_path", None) else get_workspace_path()
    workspace.mkdir(parents=True, exist_ok=True)
    create_workspace_templates(workspace, console=console)


def onboard_command(
    *,
    console: Any,
    logo: str,
    apply_recommended_tool_defaults: Callable[[Config], None],
) -> None:
    """Initialize lunaeclaw configuration and workspace."""
    from lunaeclaw.platform.config.loader import get_config_path, load_config, save_config
    from lunaeclaw.platform.utils.helpers import (
        get_env_dir,
        get_env_file,
        get_global_skills_path,
        get_mcp_home,
        get_workspace_path,
    )

    config_path = get_config_path()

    if config_path.exists():
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        console.print("  [bold]y[/bold] = overwrite with defaults (existing values will be lost)")
        console.print("  [bold]N[/bold] = refresh config, keeping existing values and adding new fields")
        if typer.confirm("Overwrite?"):
            config = Config()
            apply_recommended_tool_defaults(config)
            save_config(config)
            console.print(f"[green]✓[/green] Config reset to defaults at {config_path}")
        else:
            config = load_config(apply_profiles=False, resolve_env=False)
            apply_recommended_tool_defaults(config)
            save_config(config)
            console.print(f"[green]✓[/green] Config refreshed at {config_path} (existing values preserved)")
    else:
        config = Config()
        apply_recommended_tool_defaults(config)
        save_config(config)
        console.print(f"[green]✓[/green] Created config at {config_path}")

    workspace = get_workspace_path()
    get_env_dir()
    get_env_file().touch(exist_ok=True)
    get_mcp_home()
    get_global_skills_path()

    if not workspace.exists():
        workspace.mkdir(parents=True, exist_ok=True)
        console.print(f"[green]✓[/green] Created workspace at {workspace}")

    create_workspace_templates(workspace, console=console)

    console.print(f"\n{logo} lunaeclaw is ready!")
    console.print("\nNext steps:")
    console.print("  1. Add your API key to [cyan]~/.lunaeclaw/config.json[/cyan]")
    console.print("     Get one at: https://openrouter.ai/keys")
    console.print("  2. (Recommended) Put secrets in [cyan]~/.lunaeclaw/.env[/cyan] or [cyan]~/.lunaeclaw/env/*.env[/cyan]")
    console.print("     Use ${ENV_VAR} placeholders in config.json (apiBase/apiKey/etc.)")
    console.print("  3. Optional: install [cyan]uv[/cyan] to enable document parser MCP ([cyan]uvx[/cyan])")
    console.print("     Example: [cyan]brew install uv[/cyan]")
    console.print("  4. Chat: [cyan]lunaeclaw agent -m \"Hello!\"[/cyan]")
    console.print("\n[dim]Runtime folders: ~/.lunaeclaw/config.json, ~/.lunaeclaw/.env, ~/.lunaeclaw/env/, ~/.lunaeclaw/mcp/, ~/.lunaeclaw/skills/[/dim]")
    console.print("[dim]Default config now includes Exa MCP search and a docloader MCP template.[/dim]")
    console.print("[dim]Want Telegram/WhatsApp? See: README channel setup sections in this repo[/dim]")
