"""Curated MCP/skill catalog and health helpers for Web UI."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from nanobot.config.schema import Config, MCPServerConfig
from nanobot.utils.helpers import get_global_skills_path

_ENV_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

MCP_LIBRARY: list[dict[str, Any]] = [
    {
        "id": "exa",
        "name": "Exa Search",
        "desc": "Web search + code context (needs your own EXA_API_KEY).",
        "server_name": "exa",
        "config": MCPServerConfig(
            url="https://mcp.exa.ai/mcp?tools=web_search_exa,get_code_context_exa&exaApiKey=${EXA_API_KEY}"
        ),
    },
    {
        "id": "docloader",
        "name": "Document Loader",
        "desc": "Parse PDF/Word/PPT/Excel/images via FastMCP server.",
        "server_name": "docloader",
        "config": MCPServerConfig(
            command="uvx",
            args=["awslabs.document-loader-mcp-server@latest"],
            env={"FASTMCP_LOG_LEVEL": "ERROR"},
        ),
    },
    {
        "id": "fetch",
        "name": "Fetch",
        "desc": "HTTP fetch/extract helper MCP (suitable for docs/web text).",
        "server_name": "fetch",
        "config": MCPServerConfig(
            command="uvx",
            args=["mcp-server-fetch@latest"],
        ),
    },
    {
        "id": "github",
        "name": "GitHub MCP",
        "desc": "GitHub API MCP (requires GITHUB_TOKEN).",
        "server_name": "github_mcp",
        "config": MCPServerConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"],
            env={"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
        ),
    },
    {
        "id": "filesystem",
        "name": "Filesystem MCP",
        "desc": "Expose local directory as MCP filesystem tools.",
        "server_name": "filesystem",
        "config": MCPServerConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "."],
        ),
    },
    {
        "id": "sqlite",
        "name": "SQLite MCP",
        "desc": "SQLite query MCP (local DB inspection).",
        "server_name": "sqlite",
        "config": MCPServerConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-sqlite", "--db-path", "./data.db"],
        ),
    },
    {
        "id": "memory",
        "name": "Memory MCP",
        "desc": "Simple key-value memory MCP server.",
        "server_name": "memory_mcp",
        "config": MCPServerConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-memory"],
        ),
    },
    {
        "id": "sequential",
        "name": "Sequential Thinking MCP",
        "desc": "Step-by-step reasoning helper MCP.",
        "server_name": "sequential_thinking",
        "config": MCPServerConfig(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        ),
    },
]

SKILL_LIBRARY: list[dict[str, Any]] = [
    {"id": "memory", "name": "memory", "desc": "Persistent memory best-practice."},
    {"id": "github", "name": "github", "desc": "GitHub workflow via gh CLI."},
    {"id": "weather", "name": "weather", "desc": "Daily weather queries."},
    {"id": "attachment-analyzer", "name": "attachment-analyzer", "desc": "Document/image analysis flow."},
    {"id": "tmux", "name": "tmux", "desc": "Terminal session management."},
    {"id": "summarize", "name": "summarize", "desc": "Long-content summarization."},
]


def find_mcp_library_entry(entry_id: str) -> dict[str, Any] | None:
    wanted = (entry_id or "").strip()
    for item in MCP_LIBRARY:
        if str(item.get("id", "")).strip() == wanted:
            return item
    return None


def find_skill_library_entry(entry_id: str) -> dict[str, Any] | None:
    wanted = (entry_id or "").strip()
    for item in SKILL_LIBRARY:
        if str(item.get("id", "")).strip() == wanted:
            return item
    return None


def _extract_placeholders(text: str) -> set[str]:
    out: set[str] = set()
    for m in _ENV_PLACEHOLDER_RE.finditer(text or ""):
        out.add(m.group(1))
    return out


def _missing_placeholders(values: list[str]) -> list[str]:
    missing: set[str] = set()
    for value in values:
        for key in _extract_placeholders(value):
            if not os.environ.get(key):
                missing.add(key)
    return sorted(missing)


def evaluate_mcp_library_health(cfg: Config, item: dict[str, Any]) -> dict[str, str]:
    """Return lightweight MCP readiness status for a library entry."""
    server_name = str(item.get("server_name") or "").strip()
    if not server_name:
        return {"status": "invalid", "label": "invalid", "hint": "missing server_name"}

    server_cfg = cfg.tools.mcp_servers.get(server_name)
    if not server_cfg:
        return {"status": "not_installed", "label": "not installed", "hint": "install from library"}

    allow = set(cfg.tools.mcp_enabled_servers or [])
    deny = set(cfg.tools.mcp_disabled_servers or [])
    enabled = ((not allow) or (server_name in allow)) and (server_name not in deny)

    placeholder_values = [server_cfg.url or ""]
    if server_cfg.env:
        placeholder_values.extend(str(v) for v in server_cfg.env.values())
    missing_env = _missing_placeholders(placeholder_values)
    if missing_env:
        return {
            "status": "missing_env",
            "label": "missing env",
            "hint": ", ".join(missing_env),
        }

    if server_cfg.command and not shutil.which(server_cfg.command):
        return {
            "status": "missing_command",
            "label": "missing cmd",
            "hint": server_cfg.command,
        }

    if enabled:
        return {"status": "ready", "label": "ready", "hint": "enabled"}
    return {"status": "filtered", "label": "filtered", "hint": "installed but filtered"}


def evaluate_skill_library_health(
    cfg: Config,
    item: dict[str, Any],
    skill_rows: list[dict[str, Any]],
) -> dict[str, str]:
    """Return lightweight skill readiness status for a library entry."""
    skill_name = str(item.get("name") or "").strip()
    by_name = {str(row.get("name") or ""): row for row in skill_rows}
    row = by_name.get(skill_name)
    if not row:
        return {"status": "not_installed", "label": "not installed", "hint": "install or import skill"}
    if skill_name in set(cfg.skills.disabled or []):
        return {"status": "disabled", "label": "disabled", "hint": "enable in selection"}
    if not bool(row.get("available", False)):
        return {
            "status": "missing_deps",
            "label": "missing deps",
            "hint": str(row.get("requires") or "install required dependencies"),
        }
    return {"status": "ready", "label": "ready", "hint": "enabled"}


def _builtin_skills_root() -> Path:
    # nanobot/webui/catalog.py -> nanobot/skills
    return Path(__file__).resolve().parents[1] / "skills"


def install_skill_from_library(skill_name: str, *, overwrite: bool = False) -> tuple[bool, str]:
    """Install a built-in skill into global skills dir for user customization."""
    name = (skill_name or "").strip()
    if not name:
        return False, "skill_name is required"

    src = _builtin_skills_root() / name
    if not src.exists() or not src.is_dir() or not (src / "SKILL.md").exists():
        return False, f"built-in skill source not found: {name}"

    dst = get_global_skills_path() / name
    if dst.exists():
        if not overwrite:
            return False, f"skill already exists: {name}"
        shutil.rmtree(dst)

    shutil.copytree(src, dst)
    return True, f"installed skill: {name}"
