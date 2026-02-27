"""Subagent manager for background task execution."""

import asyncio
import json
import uuid
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.bus.events import InboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.agent.toolset_builder import ToolsetBuilder
from nanobot.agent.tooling import (
    is_mcp_server_enabled,
    normalize_name_set,
    normalize_tool_aliases,
    normalize_web_search_provider,
    should_try_exa_mcp_search,
    truncate_tool_output,
)
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.web import (
    has_exa_search_mcp,
)


class SubagentManager:
    """
    Manages background subagent execution.
    
    Subagents are lightweight agent instances that run in the background
    to handle specific tasks. They share the same LLM provider but have
    isolated context and a focused system prompt.
    """
    _TOOL_RESULT_MAX_CHARS = 12000
    
    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path,
        bus: MessageBus,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        exec_config: "ExecToolConfig | None" = None,
        restrict_to_workspace: bool = False,
        mcp_servers: dict | None = None,
        web_search_provider: str = "exa_mcp",
        mcp_enabled_servers: list[str] | None = None,
        mcp_disabled_servers: list[str] | None = None,
        mcp_enabled_tools: list[str] | None = None,
        mcp_disabled_tools: list[str] | None = None,
        tool_aliases: dict[str, str] | None = None,
        enabled_tools: list[str] | None = None,
        files_hub_exports_dir: str = "",
    ):
        from nanobot.config.schema import ExecToolConfig
        self.provider = provider
        self.workspace = workspace
        self.bus = bus
        self.model = model or provider.get_default_model()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.exec_config = exec_config or ExecToolConfig()
        self.restrict_to_workspace = restrict_to_workspace
        self._mcp_servers = mcp_servers or {}
        self.web_search_provider = self._normalize_web_search_provider(web_search_provider)
        self._mcp_enabled_servers = normalize_name_set(mcp_enabled_servers)
        self._mcp_disabled_servers = normalize_name_set(mcp_disabled_servers)
        self._mcp_enabled_tools = normalize_name_set(mcp_enabled_tools)
        self._mcp_disabled_tools = normalize_name_set(mcp_disabled_tools)
        exa_candidates = {
            name: cfg
            for name, cfg in self._mcp_servers.items()
            if self._mcp_server_enabled(name)
        }
        self._exa_mcp_configured = has_exa_search_mcp(exa_candidates)
        self._prefer_exa_mcp_web_search = self._should_try_exa_mcp_search()
        self.tool_aliases = normalize_tool_aliases(tool_aliases)
        self.enabled_tools = normalize_name_set(enabled_tools)
        self.files_hub_exports_dir = files_hub_exports_dir or ""
        self.toolset = ToolsetBuilder(
            workspace=self.workspace,
            restrict_to_workspace=self.restrict_to_workspace,
            enabled_tools=self.enabled_tools,
            exec_timeout=self.exec_config.timeout,
            files_hub_exports_dir=self.files_hub_exports_dir,
        )
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
    
    def _mcp_server_enabled(self, name: str) -> bool:
        return is_mcp_server_enabled(
            name,
            enabled_servers=self._mcp_enabled_servers,
            disabled_servers=self._mcp_disabled_servers,
        )

    @staticmethod
    def _normalize_web_search_provider(value: str | None) -> str:
        return normalize_web_search_provider(value)

    def _should_try_exa_mcp_search(self) -> bool:
        return should_try_exa_mcp_search(self.web_search_provider, self._exa_mcp_configured)

    async def spawn(
        self,
        task: str,
        label: str | None = None,
        origin_channel: str = "cli",
        origin_chat_id: str = "direct",
    ) -> str:
        """
        Spawn a subagent to execute a task in the background.
        
        Args:
            task: The task description for the subagent.
            label: Optional human-readable label for the task.
            origin_channel: The channel to announce results to.
            origin_chat_id: The chat ID to announce results to.
        
        Returns:
            Status message indicating the subagent was started.
        """
        task_id = str(uuid.uuid4())[:8]
        display_label = label or task[:30] + ("..." if len(task) > 30 else "")
        
        origin = {
            "channel": origin_channel,
            "chat_id": origin_chat_id,
        }
        
        # Create background task
        bg_task = asyncio.create_task(
            self._run_subagent(task_id, task, display_label, origin)
        )
        self._running_tasks[task_id] = bg_task
        
        # Cleanup when done
        bg_task.add_done_callback(lambda _: self._running_tasks.pop(task_id, None))
        
        logger.info("Spawned subagent [{}]: {}", task_id, display_label)
        return f"Subagent [{display_label}] started (id: {task_id}). I'll notify you when it completes."
    
    async def _run_subagent(
        self,
        task_id: str,
        task: str,
        label: str,
        origin: dict[str, str],
    ) -> None:
        """Execute the subagent task and announce the result."""
        logger.info("Subagent [{}] starting task: {}", task_id, label)
        active_model = self.model

        try:
            async with AsyncExitStack() as mcp_stack:
                # Build subagent tools (no message tool, no spawn tool)
                tools = ToolRegistry()
                self.toolset.register_core_tools(tools)
                self._register_subagent_web_search_initial()
                self._apply_configured_tool_aliases(tools, stage="startup")

                if self._mcp_servers:
                    from nanobot.agent.tools.mcp import connect_mcp_servers
                    await connect_mcp_servers(
                        self._mcp_servers,
                        tools,
                        mcp_stack,
                        enabled_servers=self._mcp_enabled_servers or None,
                        disabled_servers=self._mcp_disabled_servers or None,
                        enabled_tools=self._mcp_enabled_tools or None,
                        disabled_tools=self._mcp_disabled_tools or None,
                    )
                    if self._prefer_exa_mcp_web_search and self.toolset.tool_enabled("web_search"):
                        if not self._install_exa_web_search_alias_if_available(tools):
                            logger.warning(
                                "Subagent [{}]: Exa MCP is configured but 'web_search_exa' tool was not registered",
                                task_id,
                            )
                    self._apply_configured_tool_aliases(tools, stage="mcp")
            
                # Build messages with subagent-specific prompt
                system_prompt = self._build_subagent_prompt(task)
                messages: list[dict[str, Any]] = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": task},
                ]
                
                # Run agent loop (limited iterations)
                max_iterations = 15
                iteration = 0
                final_result: str | None = None
                
                while iteration < max_iterations:
                    iteration += 1
                    
                    response = await self.provider.chat(
                        messages=messages,
                        tools=tools.get_definitions(),
                        model=active_model,
                        temperature=self.temperature,
                        max_tokens=self.max_tokens,
                    )
                    
                    if response.has_tool_calls:
                        # Add assistant message with tool calls
                        tool_call_dicts = [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                                },
                            }
                            for tc in response.tool_calls
                        ]
                        messages.append({
                            "role": "assistant",
                            "content": response.content or "",
                            "tool_calls": tool_call_dicts,
                        })
                        
                        # Execute tools
                        for tool_call in response.tool_calls:
                            args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                            logger.debug("Subagent [{}] executing: {} with arguments: {}", task_id, tool_call.name, args_str)
                            result = await tools.execute(tool_call.name, tool_call.arguments)
                            result = truncate_tool_output(
                                result,
                                tool_call.name,
                                limit=self._TOOL_RESULT_MAX_CHARS,
                                source_label="nanobot subagent",
                            )
                            messages.append({
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": tool_call.name,
                                "content": result,
                            })
                    else:
                        final_result = response.content
                        break
                
                if final_result is None:
                    final_result = "Task completed but no final response was generated."
                
                logger.info("Subagent [{}] completed successfully", task_id)
                await self._announce_result(task_id, label, task, final_result, origin, "ok")

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logger.error("Subagent [{}] failed: {}", task_id, e)
            await self._announce_result(task_id, label, task, error_msg, origin, "error")

    def _register_subagent_web_search_initial(self) -> None:
        self.toolset.register_web_search_initial(
            web_search_provider=self.web_search_provider,
            exa_mcp_configured=self._exa_mcp_configured,
            prefer_exa_mcp_web_search=self._prefer_exa_mcp_web_search,
            owner="Subagent",
        )

    def _install_exa_web_search_alias_if_available(self, tools: ToolRegistry) -> bool:
        return self.toolset.install_exa_web_search_alias(tools, owner="Subagent")

    def _apply_configured_tool_aliases(self, tools: ToolRegistry, stage: str) -> None:
        self.toolset.apply_configured_aliases(
            tools,
            aliases=self.tool_aliases,
            stage=stage,
            owner="Subagent",
        )
    
    async def _announce_result(
        self,
        task_id: str,
        label: str,
        task: str,
        result: str,
        origin: dict[str, str],
        status: str,
    ) -> None:
        """Announce the subagent result to the main agent via the message bus."""
        status_text = "completed successfully" if status == "ok" else "failed"
        
        announce_content = f"""[Subagent '{label}' {status_text}]

Task: {task}

Result:
{result}

Summarize this naturally for the user. Keep it brief (1-2 sentences). Do not mention technical details like "subagent" or task IDs."""
        
        # Inject as system message to trigger main agent
        msg = InboundMessage(
            channel="system",
            sender_id="subagent",
            chat_id=f"{origin['channel']}:{origin['chat_id']}",
            content=announce_content,
        )
        
        await self.bus.publish_inbound(msg)
        logger.debug("Subagent [{}] announced result to {}:{}", task_id, origin['channel'], origin['chat_id'])
    
    def _build_subagent_prompt(self, task: str) -> str:
        """Build a focused system prompt for the subagent."""
        from datetime import datetime
        import time as _time
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"

        return f"""# Subagent

## Current Time
{now} ({tz})

You are a subagent spawned by the main agent to complete a specific task.

## Rules
1. Stay focused - complete only the assigned task, nothing else
2. Your final response will be reported back to the main agent
3. Do not initiate conversations or take on side tasks
4. Be concise but informative in your findings

## What You Can Do
- Read and write files in the workspace
- Execute shell commands
- Search the web and fetch web pages
- Complete the task thoroughly

## What You Cannot Do
- Send messages directly to users (no message tool available)
- Spawn other subagents
- Access the main agent's conversation history

## Workspace
Your workspace is at: {self.workspace}
Skills are available at: {self.workspace}/skills/ (read SKILL.md files as needed)

When you have completed the task, provide a clear summary of your findings or actions."""
    
    def get_running_count(self) -> int:
        """Return the number of currently running subagents."""
        return len(self._running_tasks)
