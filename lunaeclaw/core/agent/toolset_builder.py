"""Shared toolset builder for main agent and subagent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from lunaeclaw.capabilities.tools.alias import install_tool_aliases
from lunaeclaw.capabilities.tools.claude_code import ClaudeCodeTool
from lunaeclaw.capabilities.tools.cron import CronTool
from lunaeclaw.capabilities.tools.export import ExportFileTool
from lunaeclaw.capabilities.tools.filesystem import (
    EditFileTool,
    ListDirTool,
    ReadFileTool,
    WriteFileTool,
)
from lunaeclaw.capabilities.tools.media import FilesHubTool
from lunaeclaw.capabilities.tools.message import MessageTool
from lunaeclaw.capabilities.tools.registry import ToolRegistry
from lunaeclaw.capabilities.tools.shell import ExecTool
from lunaeclaw.capabilities.tools.spawn import SpawnTool
from lunaeclaw.capabilities.tools.web import WeatherTool, WebFetchTool, install_exa_web_search_alias
from lunaeclaw.core.agent.tooling import is_tool_enabled
from lunaeclaw.platform.utils.helpers import get_exports_dir, get_media_dir


class ToolsetBuilder:
    """Build a consistent built-in toolset across agent runtimes."""

    def __init__(
        self,
        *,
        workspace: Path,
        restrict_to_workspace: bool,
        enabled_tools: set[str],
        exec_timeout: int,
        files_hub_exports_dir: str = "",
    ) -> None:
        self.workspace = workspace
        self.restrict_to_workspace = restrict_to_workspace
        self.enabled_tools = enabled_tools
        self.exec_timeout = exec_timeout
        self.files_hub_exports_dir = files_hub_exports_dir or ""

        self._exports_dir = get_exports_dir(self.files_hub_exports_dir)
        self._allowed_dir = self.workspace if self.restrict_to_workspace else None
        self._extra_read_dirs = [get_media_dir(), self._exports_dir] if self.restrict_to_workspace else None

    @property
    def exports_dir(self) -> Path:
        return self._exports_dir

    def tool_enabled(self, name: str) -> bool:
        return is_tool_enabled(self.enabled_tools, name)

    def register_core_tools(self, registry: ToolRegistry) -> None:
        """Register shared built-in tools used by both main agent and subagents."""
        self._register_file_tools(registry)

        if self.tool_enabled("exec"):
            registry.register(
                ExecTool(
                    working_dir=str(self.workspace),
                    timeout=self.exec_timeout,
                    restrict_to_workspace=self.restrict_to_workspace,
                )
            )

        if self.tool_enabled("web_fetch"):
            registry.register(WebFetchTool())
        if self.tool_enabled("files_hub"):
            registry.register(FilesHubTool(exports_dir=self._exports_dir))
        if self.tool_enabled("export_file"):
            registry.register(ExportFileTool(exports_dir=self._exports_dir))
        if self.tool_enabled("weather"):
            registry.register(WeatherTool())

    def register_agent_extras(
        self,
        registry: ToolRegistry,
        *,
        send_callback: Any | None = None,
        message_output_sanitizer: Any | None = None,
        spawn_manager: Any | None = None,
        cron_service: Any | None = None,
        claude_code_config: Any | None = None,
    ) -> None:
        """Register tools only available in the main agent loop."""
        if self.tool_enabled("claude_code") and claude_code_config and bool(getattr(claude_code_config, "enabled", False)):
            registry.register(
                ClaudeCodeTool(
                    workspace=self.workspace,
                    config=claude_code_config,
                    restrict_to_workspace=self.restrict_to_workspace,
                )
            )
        if self.tool_enabled("message") and send_callback is not None:
            registry.register(
                MessageTool(
                    send_callback=send_callback,
                    output_sanitizer=message_output_sanitizer,
                )
            )
        if self.tool_enabled("spawn") and spawn_manager is not None:
            registry.register(SpawnTool(manager=spawn_manager))
        if self.tool_enabled("cron") and cron_service is not None:
            registry.register(CronTool(cron_service))

    def register_web_search_initial(
        self,
        *,
        web_search_provider: str,
        exa_mcp_configured: bool,
        prefer_exa_mcp_web_search: bool,
        owner: str = "",
    ) -> None:
        """Log startup web_search registration state before MCP connects."""
        if not self.tool_enabled("web_search"):
            return

        prefix = f"{owner}: " if owner else ""

        if web_search_provider == "disabled":
            logger.info("{}web_search provider is disabled; skipping web_search tool registration", prefix)
            return
        if web_search_provider == "exa_mcp" and not exa_mcp_configured:
            logger.warning(
                "{}web_search provider is exa_mcp but no Exa MCP server is configured; web_search unavailable",
                prefix,
            )
            return
        if prefer_exa_mcp_web_search:
            logger.info("{}Exa MCP detected; deferring built-in web_search registration until MCP connects", prefix)
            return

        logger.warning("{}web_search enabled but Exa MCP is not configured; web_search unavailable", prefix)

    def install_exa_web_search_alias(self, registry: ToolRegistry, *, owner: str = "") -> bool:
        """Install web_search alias backed by MCP Exa tool when available."""
        if not self.tool_enabled("web_search"):
            return False

        wrapped = install_exa_web_search_alias(registry)
        if not wrapped:
            return False

        prefix = f"{owner}: " if owner else ""
        logger.info("{}registered web_search compatibility alias -> {}", prefix, wrapped)
        return True

    def apply_configured_aliases(
        self,
        registry: ToolRegistry,
        *,
        aliases: dict[str, str],
        stage: str,
        owner: str = "",
    ) -> None:
        """Install user-configured aliases after tool registration stages."""
        if not aliases:
            return

        summary = install_tool_aliases(registry, aliases)
        prefix = f"{owner}: " if owner else ""

        if summary["installed"]:
            logger.info(
                "{}configured tool aliases applied ({}): {}",
                prefix,
                stage,
                ", ".join(summary["installed"]),
            )
        if summary["unresolved"]:
            logger.debug(
                "{}configured tool aliases unresolved ({}): {}",
                prefix,
                stage,
                ", ".join(summary["unresolved"]),
            )

    def _register_file_tools(self, registry: ToolRegistry) -> None:
        file_tools = (
            ("read_file", ReadFileTool),
            ("write_file", WriteFileTool),
            ("edit_file", EditFileTool),
            ("list_dir", ListDirTool),
        )

        for name, cls in file_tools:
            if not self.tool_enabled(name):
                continue
            if name in {"read_file", "list_dir"}:
                registry.register(
                    cls(
                        workspace=self.workspace,
                        allowed_dir=self._allowed_dir,
                        extra_allowed_dirs=self._extra_read_dirs,
                    )
                )
            else:
                registry.register(cls(workspace=self.workspace, allowed_dir=self._allowed_dir))
