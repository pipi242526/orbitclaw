"""Utility functions for orbitclaw."""

import os
from datetime import datetime
from pathlib import Path


def ensure_dir(path: Path) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_path() -> Path:
    """Get the orbitclaw data directory (default ~/.orbitclaw, override via ORBITCLAW_DATA_DIR)."""
    override = (os.environ.get("ORBITCLAW_DATA_DIR") or "").strip()
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            path = (Path.home() / path).resolve()
        return ensure_dir(path)
    return ensure_dir(Path.home() / ".orbitclaw")


def get_config_dir() -> Path:
    """Get the configuration directory (~/.orbitclaw)."""
    return get_data_path()


def get_config_file() -> Path:
    """Get the main config file path (~/.orbitclaw/config.json)."""
    return get_config_dir() / "config.json"


def get_env_dir() -> Path:
    """Get the env helper directory (~/.orbitclaw/env)."""
    return ensure_dir(get_data_path() / "env")


def get_env_file() -> Path:
    """Get the primary env helper file (~/.orbitclaw/.env)."""
    return get_data_path() / ".env"


def get_mcp_home() -> Path:
    """Get the MCP runtime home (~/.orbitclaw/mcp)."""
    return ensure_dir(get_data_path() / "mcp")


def get_mcp_bin_dir() -> Path:
    """Get the MCP local bin directory (~/.orbitclaw/mcp/bin)."""
    return ensure_dir(get_mcp_home() / "bin")


def get_mcp_data_dir() -> Path:
    """Get the MCP local data/cache directory (~/.orbitclaw/mcp/data)."""
    return ensure_dir(get_mcp_home() / "data")


def get_media_dir() -> Path:
    """Get the downloaded media directory (~/.orbitclaw/media)."""
    return ensure_dir(get_data_path() / "media")


def get_exports_dir(custom_dir: str | Path | None = None) -> Path:
    """Get the generated output files directory.

    If `custom_dir` is provided, relative paths are resolved under ~/.orbitclaw.
    """
    if custom_dir:
        p = Path(custom_dir).expanduser()
        if not p.is_absolute():
            p = get_data_path() / p
        return ensure_dir(p)
    return ensure_dir(get_data_path() / "exports")


def get_history_dir() -> Path:
    """Get CLI history directory (~/.orbitclaw/history)."""
    return ensure_dir(get_data_path() / "history")


def get_cli_history_file() -> Path:
    """Get CLI history file path."""
    return get_history_dir() / "cli_history"


def get_bridge_dir() -> Path:
    """Get bridge working directory (~/.orbitclaw/bridge)."""
    return ensure_dir(get_data_path() / "bridge")


def get_workspace_path(workspace: str | None = None) -> Path:
    """
    Get the workspace path.

    Args:
        workspace: Optional workspace path. Defaults to <data_dir>/workspace.

    Returns:
        Expanded and ensured workspace path.
    """
    if workspace:
        path = Path(workspace).expanduser()
    else:
        path = get_data_path() / "workspace"
    return ensure_dir(path)


def get_sessions_path() -> Path:
    """Get the sessions storage directory."""
    return ensure_dir(get_data_path() / "sessions")


def get_skills_path(workspace: Path | None = None) -> Path:
    """Get the skills directory within the workspace."""
    ws = workspace or get_workspace_path()
    return ensure_dir(ws / "skills")


def get_global_skills_path() -> Path:
    """Get the global custom skills directory (~/.orbitclaw/skills)."""
    return ensure_dir(get_data_path() / "skills")


def timestamp() -> str:
    """Get current timestamp in ISO format."""
    return datetime.now().isoformat()


def truncate_string(s: str, max_len: int = 100, suffix: str = "...") -> str:
    """Truncate a string to max length, adding suffix if truncated."""
    if len(s) <= max_len:
        return s
    return s[: max_len - len(suffix)] + suffix


def safe_filename(name: str) -> str:
    """Convert a string to a safe filename."""
    # Replace unsafe characters
    unsafe = '<>:"/\\|?*'
    for char in unsafe:
        name = name.replace(char, "_")
    return name.strip()


def parse_session_key(key: str) -> tuple[str, str]:
    """
    Parse a session key into channel and chat_id.

    Args:
        key: Session key in format "channel:chat_id"

    Returns:
        Tuple of (channel, chat_id)
    """
    parts = key.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid session key: {key}")
    return parts[0], parts[1]
