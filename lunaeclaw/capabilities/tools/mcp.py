"""MCP client: connects to MCP servers and wraps their tools as native lunaeclaw tools."""

import asyncio
import os
from contextlib import AsyncExitStack
from typing import Any

import httpx
from loguru import logger

from lunaeclaw.capabilities.tools.base import Tool
from lunaeclaw.capabilities.tools.registry import ToolRegistry
from lunaeclaw.platform.utils.helpers import (
    get_data_path,
    get_mcp_bin_dir,
    get_mcp_data_dir,
    get_mcp_home,
)


class MCPToolWrapper(Tool):
    """Wraps a single MCP server tool as a lunaeclaw Tool."""

    def __init__(self, session, server_name: str, tool_def, tool_timeout: int = 30):
        self._session = session
        self._original_name = tool_def.name
        self._name = f"mcp_{server_name}_{tool_def.name}"
        self._description = tool_def.description or tool_def.name
        self._parameters = tool_def.inputSchema or {"type": "object", "properties": {}}
        self._tool_timeout = tool_timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        from mcp import types
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(self._original_name, arguments=kwargs),
                timeout=self._tool_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("MCP tool '{}' timed out after {}s", self._name, self._tool_timeout)
            return f"(MCP tool call timed out after {self._tool_timeout}s)"
        parts = []
        for block in result.content:
            if isinstance(block, types.TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts) or "(no output)"


async def connect_mcp_servers(
    mcp_servers: dict,
    registry: ToolRegistry,
    stack: AsyncExitStack,
    enabled_servers: set[str] | None = None,
    disabled_servers: set[str] | None = None,
    enabled_tools: set[str] | None = None,
    disabled_tools: set[str] | None = None,
) -> None:
    """Connect to configured MCP servers and register their tools."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    mcp_home = get_mcp_home()
    mcp_bin = get_mcp_bin_dir()
    mcp_data = get_mcp_data_dir()
    nanobot_data = get_data_path()

    for name, cfg in mcp_servers.items():
        lname = str(name).lower()
        if enabled_servers and lname not in enabled_servers:
            logger.info("MCP server '{}': skipped (not in tools.mcp_enabled_servers)", name)
            continue
        if disabled_servers and lname in disabled_servers:
            logger.info("MCP server '{}': skipped (in tools.mcp_disabled_servers)", name)
            continue
        try:
            if cfg.command:
                merged_env = dict(cfg.env or {})
                merged_env.setdefault("LUNAECLAW_MCP_HOME", str(mcp_home))
                merged_env.setdefault("LUNAECLAW_MCP_BIN", str(mcp_bin))
                merged_env.setdefault("LUNAECLAW_MCP_DATA", str(mcp_data))
                # Make locally installed wrappers/scripts discoverable by stdio MCP servers.
                current_path = merged_env.get("PATH") or os.environ.get("PATH", "")
                merged_env["PATH"] = (
                    f"{mcp_bin}{os.pathsep + current_path if current_path else ''}"
                )
                # AWS document-loader MCP restricts file access to cwd by default.
                # Expand base directory to ~/.lunaeclaw so it can read downloaded attachments
                # in ~/.lunaeclaw/media and workspace files in ~/.lunaeclaw/workspace.
                (cfg.command or "").lower()
                args_joined = " ".join(str(a).lower() for a in (cfg.args or []))
                if lname == "docloader" or "document-loader-mcp-server" in args_joined or "document_loader_mcp_server" in args_joined:
                    merged_env.setdefault("DOCUMENT_BASE_DIR", str(nanobot_data))
                params = StdioServerParameters(
                    command=cfg.command, args=cfg.args, env=merged_env or None
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            elif cfg.url:
                from mcp.client.streamable_http import streamable_http_client
                # Always provide an explicit client to avoid httpx default timeouts
                # interfering with per-tool MCP timeouts.
                http_client = await stack.enter_async_context(
                    httpx.AsyncClient(
                        headers=cfg.headers or None,
                        follow_redirects=True,
                        timeout=None,
                    )
                )
                read, write, _ = await stack.enter_async_context(
                    streamable_http_client(cfg.url, http_client=http_client)
                )
            else:
                logger.warning("MCP server '{}': no command or url configured, skipping", name)
                continue

            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            tools = await session.list_tools()
            registered = 0
            skipped = 0
            for tool_def in tools.tools:
                wrapped_name = f"mcp_{name}_{tool_def.name}".lower()
                original_name = str(tool_def.name).lower()
                scoped_name = f"{name}.{tool_def.name}".lower()
                aliases = {wrapped_name, original_name, scoped_name}
                if enabled_tools and not (aliases & enabled_tools):
                    skipped += 1
                    logger.debug("MCP: skipped tool '{}' from server '{}' (not in allowlist)", tool_def.name, name)
                    continue
                if disabled_tools and (aliases & disabled_tools):
                    skipped += 1
                    logger.debug("MCP: skipped tool '{}' from server '{}' (in denylist)", tool_def.name, name)
                    continue
                wrapper = MCPToolWrapper(session, name, tool_def, tool_timeout=cfg.tool_timeout)
                registry.register(wrapper)
                registered += 1
                logger.debug("MCP: registered tool '{}' from server '{}'", wrapper.name, name)

            logger.info(
                "MCP server '{}': connected, {} tools registered{}",
                name,
                registered,
                f" ({skipped} filtered)" if skipped else "",
            )
        except Exception as e:
            logger.error("MCP server '{}': failed to connect: {}", name, e)
