"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import gc
import re
from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

from loguru import logger

from lunaeclaw.capabilities.tools.cron import CronTool
from lunaeclaw.capabilities.tools.message import MessageTool
from lunaeclaw.capabilities.tools.registry import ToolRegistry
from lunaeclaw.capabilities.tools.spawn import SpawnTool
from lunaeclaw.capabilities.tools.web import (
    has_exa_search_mcp,
)
from lunaeclaw.core.agent.subagent import SubagentManager
from lunaeclaw.core.agent.tooling import (
    is_mcp_server_enabled,
    is_tool_enabled,
    normalize_name_set,
    normalize_tool_aliases,
    normalize_web_search_provider,
    should_try_exa_mcp_search,
    truncate_tool_output,
)
from lunaeclaw.core.agent.toolset_builder import ToolsetBuilder
from lunaeclaw.core.agent.turn_commands import (
    cmd_help,
    cmd_model,
    cmd_new,
    dispatch_command,
    parse_slash_command,
    register_builtin_commands,
)
from lunaeclaw.core.agent.turn_handlers import (
    handle_inbound_message,
    process_direct_message,
    process_message,
)
from lunaeclaw.core.agent.turn_runner import (
    run_agent_iterations,
)
from lunaeclaw.core.bus.events import InboundMessage, OutboundMessage
from lunaeclaw.core.bus.queue import MessageBus
from lunaeclaw.core.context.context import ContextBuilder
from lunaeclaw.core.context.memory import MemoryStore
from lunaeclaw.core.policy.policy_pipeline import PolicyPipeline
from lunaeclaw.platform.providers.base import LLMProvider
from lunaeclaw.services.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from lunaeclaw.platform.config.schema import ClaudeCodeToolConfig, ExecToolConfig
    from lunaeclaw.services.cron.service import CronService


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory, skills
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back
    """
    _CHANNEL_PROCESSING_NOTICE_DELAY_S = 8.0
    _TOOL_RESULT_MAX_CHARS = 20000
    _GC_EVERY_TURNS = 12
    _SESSION_CACHE_MAX_ENTRIES = 16

    @dataclass(frozen=True)
    class _CommandSpec:
        name: str
        help_en: str
        help_zh: str
        handler: str

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 20,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        memory_window: int = 50,
        exec_config: ExecToolConfig | None = None,
        claude_code_config: "ClaudeCodeToolConfig | None" = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        web_search_provider: str = "exa_mcp",
        mcp_enabled_servers: list[str] | None = None,
        mcp_disabled_servers: list[str] | None = None,
        mcp_enabled_tools: list[str] | None = None,
        mcp_disabled_tools: list[str] | None = None,
        tool_aliases: dict[str, str] | None = None,
        enabled_tools: list[str] | None = None,
        disabled_skills: list[str] | None = None,
        reply_language: str = "auto",
        auto_reply_fallback_language: str = "zh-CN",
        cross_lingual_search: bool = True,
        files_hub_exports_dir: str = "",
        max_history_chars: int = 32000,
        max_memory_context_chars: int = 12000,
        max_background_context_chars: int = 22000,
        max_inline_image_bytes: int = 400000,
        auto_compact_background: bool = True,
        system_prompt_cache_ttl_seconds: int = 20,
        session_cache_max_entries: int = _SESSION_CACHE_MAX_ENTRIES,
        gc_every_turns: int = _GC_EVERY_TURNS,
        turn_timeout_seconds: int = 45,
    ):
        from lunaeclaw.platform.config.schema import ExecToolConfig
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.exec_config = exec_config or ExecToolConfig()
        self.claude_code_config = claude_code_config
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self.enabled_tools = normalize_name_set(enabled_tools)
        self.disabled_skills = normalize_name_set(disabled_skills)
        self.web_search_provider = normalize_web_search_provider(web_search_provider)
        self.tool_aliases = normalize_tool_aliases(tool_aliases)
        self.files_hub_exports_dir = files_hub_exports_dir or ""
        self._gc_every_turns = max(0, int(gc_every_turns or 0))
        self._turn_timeout_seconds = max(5, int(turn_timeout_seconds or 45))

        self.context = ContextBuilder(
            workspace,
            disabled_skills=self.disabled_skills,
            reply_language_preference=reply_language,
            auto_reply_fallback_language=auto_reply_fallback_language,
            cross_lingual_search=cross_lingual_search,
            max_history_chars=max_history_chars,
            max_memory_context_chars=max_memory_context_chars,
            max_background_context_chars=max_background_context_chars,
            max_inline_image_bytes=max_inline_image_bytes,
            auto_compact_background=auto_compact_background,
            system_prompt_cache_ttl_seconds=system_prompt_cache_ttl_seconds,
        )
        self.sessions = session_manager or SessionManager(
            workspace,
            max_cache_entries=max(1, int(session_cache_max_entries or self._SESSION_CACHE_MAX_ENTRIES)),
        )
        self.memory_store = MemoryStore(workspace)
        self.tools = ToolRegistry()
        self.toolset = ToolsetBuilder(
            workspace=workspace,
            restrict_to_workspace=restrict_to_workspace,
            enabled_tools=self.enabled_tools,
            exec_timeout=self.exec_config.timeout,
            files_hub_exports_dir=self.files_hub_exports_dir,
        )
        self._mcp_servers = mcp_servers or {}
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
        self.subagents = SubagentManager(
            provider=provider,
            workspace=workspace,
            bus=bus,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            exec_config=self.exec_config,
            restrict_to_workspace=restrict_to_workspace,
            mcp_servers=self._mcp_servers,
            web_search_provider=self.web_search_provider,
            mcp_enabled_servers=mcp_enabled_servers,
            mcp_disabled_servers=mcp_disabled_servers,
            mcp_enabled_tools=mcp_enabled_tools,
            mcp_disabled_tools=mcp_disabled_tools,
            tool_aliases=self.tool_aliases,
            enabled_tools=enabled_tools,
            files_hub_exports_dir=self.files_hub_exports_dir,
        )
        self.policy = PolicyPipeline(
            provider=self.provider,
            context=self.context,
            default_model=self.model,
            max_tokens=self.max_tokens,
            strip_think=self._strip_think,
        )

        self._running = False
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._consolidating: set[str] = set()  # Session keys with consolidation in progress
        self._consolidation_tasks: set[asyncio.Task] = set()  # Strong refs to in-flight tasks
        self._consolidation_locks: dict[str, asyncio.Lock] = {}
        self._processed_turns = 0
        self._command_specs: dict[str, AgentLoop._CommandSpec] = {}
        self._command_aliases: dict[str, str] = {}
        self._register_default_tools()
        self._register_builtin_commands()

    def _tool_enabled(self, name: str) -> bool:
        return is_tool_enabled(self.enabled_tools, name)

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

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        self.toolset.register_core_tools(self.tools)
        self._register_web_search_tool_initial()
        self.toolset.register_agent_extras(
            self.tools,
            send_callback=self.bus.publish_outbound,
            message_output_sanitizer=self.policy.sanitize_user_visible_output,
            spawn_manager=self.subagents,
            cron_service=self.cron_service,
            claude_code_config=self.claude_code_config,
        )
        self._apply_configured_tool_aliases(stage="startup")

    def _register_web_search_tool_initial(self) -> None:
        self.toolset.register_web_search_initial(
            web_search_provider=self.web_search_provider,
            exa_mcp_configured=self._exa_mcp_configured,
            prefer_exa_mcp_web_search=self._prefer_exa_mcp_web_search,
        )

    def _install_exa_web_search_alias_if_available(self) -> bool:
        return self.toolset.install_exa_web_search_alias(self.tools)

    def _apply_configured_tool_aliases(self, stage: str) -> None:
        self.toolset.apply_configured_aliases(
            self.tools,
            aliases=self.tool_aliases,
            stage=stage,
        )

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from lunaeclaw.capabilities.tools.mcp import connect_mcp_servers
        try:
            self._mcp_stack = AsyncExitStack()
            await self._mcp_stack.__aenter__()
            await connect_mcp_servers(
                self._mcp_servers,
                self.tools,
                self._mcp_stack,
                enabled_servers=self._mcp_enabled_servers or None,
                disabled_servers=self._mcp_disabled_servers or None,
                enabled_tools=self._mcp_enabled_tools or None,
                disabled_tools=self._mcp_disabled_tools or None,
            )
            if self._prefer_exa_mcp_web_search:
                if not self._install_exa_web_search_alias_if_available():
                    logger.warning("Exa MCP is configured but 'web_search_exa' tool was not registered")
            self._apply_configured_tool_aliases(stage="mcp")
            self._mcp_connected = True
        except Exception as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._mcp_stack:
                try:
                    await self._mcp_stack.aclose()
                except Exception:
                    pass
                self._mcp_stack = None
        finally:
            self._mcp_connecting = False

    def _set_tool_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Update context for all tools that need routing info."""
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.set_context(channel, chat_id, message_id)

        if spawn_tool := self.tools.get("spawn"):
            if isinstance(spawn_tool, SpawnTool):
                spawn_tool.set_context(channel, chat_id)

        if cron_tool := self.tools.get("cron"):
            if isinstance(cron_tool, CronTool):
                cron_tool.set_context(channel, chat_id)

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think>…</think> blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip() or None

    async def _enforce_reply_language(
        self,
        *,
        user_message: str,
        draft_reply: str,
        model: str | None,
    ) -> str:
        return await self.policy.enforce_final_reply(
            user_message=user_message,
            draft_reply=draft_reply,
            model=model,
        )

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""
        def _fmt(tc):
            val = next(iter(tc.arguments.values()), None) if tc.arguments else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    def _processing_notice_text(self, user_message: str) -> str:
        return self.policy.processing_notice(user_message=user_message)

    @staticmethod
    def _processing_notice_delay_for_channel(channel: str) -> float:
        """Return per-channel delay before sending a processing placeholder."""
        c = (channel or "").lower()
        if c == "telegram":
            return 4.0
        if c in {"discord", "feishu", "qq"}:
            return 6.0
        return AgentLoop._CHANNEL_PROCESSING_NOTICE_DELAY_S

    def _effective_model_for_session(self, session: Session | None) -> str:
        if not session:
            return self.model
        override = str(session.metadata.get("model_override", "")).strip()
        return override or self.model

    def _truncate_tool_result(self, result: str, tool_name: str) -> str:
        return truncate_tool_output(
            result,
            tool_name,
            limit=self._TOOL_RESULT_MAX_CHARS,
            source_label="lunaeclaw",
        )

    def _format_user_error(self, err: Exception, *, user_message: str | None = None) -> str:
        return self.policy.format_user_error(err, user_message=user_message)

    def register_command(
        self,
        *,
        name: str,
        handler: str,
        help_en: str,
        help_zh: str,
        aliases: list[str] | None = None,
    ) -> None:
        """Register a slash command and optional aliases.

        This keeps command extension declarative: add one registration entry, then
        implement the handler method.
        """
        key = (name or "").strip().lower().lstrip("/")
        if not key:
            raise ValueError("command name cannot be empty")
        if not hasattr(self, handler):
            raise ValueError(f"command handler not found: {handler}")
        self._command_specs[key] = self._CommandSpec(
            name=key,
            help_en=help_en,
            help_zh=help_zh,
            handler=handler,
        )
        for alias in aliases or []:
            a = (alias or "").strip().lower().lstrip("/")
            if a:
                self._command_aliases[a] = key

    def _register_builtin_commands(self) -> None:
        # Command extension template:
        # 1) Implement handler: `async def _cmd_xxx(...)->OutboundMessage`
        # 2) Register it once here via `register_command(...)`
        # 3) Keep user-facing strings in PolicyPipeline (not in loop)
        # 4) Add tests for routing + help listing + output text
        register_builtin_commands(self)

    @staticmethod
    def _parse_slash_command(text: str) -> tuple[str, str] | None:
        return parse_slash_command(text)

    async def _dispatch_command(
        self,
        *,
        command_name: str,
        command_arg: str,
        msg: InboundMessage,
        session: Session,
        mk_out: Callable[[str], OutboundMessage],
    ) -> OutboundMessage | None:
        return await dispatch_command(
            self,
            command_name=command_name,
            command_arg=command_arg,
            msg=msg,
            session=session,
            mk_out=mk_out,
        )

    async def _cmd_new(
        self,
        *,
        command_arg: str,
        msg: InboundMessage,
        session: Session,
        mk_out: Callable[[str], OutboundMessage],
    ) -> OutboundMessage:
        return await cmd_new(
            self,
            command_arg=command_arg,
            msg=msg,
            session=session,
            mk_out=mk_out,
        )

    async def _cmd_help(
        self,
        *,
        command_arg: str,
        msg: InboundMessage,
        session: Session,
        mk_out: Callable[[str], OutboundMessage],
    ) -> OutboundMessage:
        return await cmd_help(
            self,
            command_arg=command_arg,
            msg=msg,
            session=session,
            mk_out=mk_out,
        )

    async def _cmd_model(
        self,
        *,
        command_arg: str,
        msg: InboundMessage,
        session: Session,
        mk_out: Callable[[str], OutboundMessage],
    ) -> OutboundMessage:
        return await cmd_model(
            self,
            command_arg=command_arg,
            msg=msg,
            session=session,
            mk_out=mk_out,
        )

    def _maybe_release_memory(self, active_session_key: str | None = None) -> None:
        """Periodic lightweight cleanup for long-running gateway processes."""
        self._processed_turns += 1
        keep = {active_session_key} if active_session_key else None
        try:
            self.sessions.prune_cache(keep_keys=keep)
        except Exception:
            logger.debug("Session cache prune skipped")
        if self._gc_every_turns > 0 and self._processed_turns % self._gc_every_turns == 0:
            gc.collect()

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        model: str | None = None,
        emit_tool_hints: bool = True,
        user_message: str = "",
    ) -> tuple[str | None, list[str]]:
        """Run the agent iteration loop. Returns (final_content, tools_used)."""
        active_model = model or self.model
        return await run_agent_iterations(
            provider=self.provider,
            context=self.context,
            tools=self.tools,
            initial_messages=initial_messages,
            max_iterations=self.max_iterations,
            model=active_model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            on_progress=on_progress,
            emit_tool_hints=emit_tool_hints,
            user_message=user_message,
            strip_think=self._strip_think,
            tool_hint=self._tool_hint,
            processing_notice_text=self._processing_notice_text,
            truncate_tool_result=self._truncate_tool_result,
        )

    async def run(self) -> None:
        """Run the agent loop, processing messages from the bus."""
        self._running = True
        await self._connect_mcp()
        logger.info("Agent loop started")

        while self._running:
            try:
                msg = await asyncio.wait_for(
                    self.bus.consume_inbound(),
                    timeout=1.0
                )
                await self._handle_inbound_message(msg)
            except asyncio.TimeoutError:
                continue

    async def _handle_inbound_message(self, msg: InboundMessage) -> None:
        """Handle one inbound turn and publish outbound response/errors."""
        await handle_inbound_message(self, msg)

    async def close_mcp(self) -> None:
        """Close MCP connections."""
        if self._mcp_stack:
            try:
                await self._mcp_stack.aclose()
            except (RuntimeError, BaseExceptionGroup):
                pass  # MCP SDK cancel scope cleanup is noisy but harmless
            self._mcp_stack = None

    def stop(self) -> None:
        """Stop the agent loop."""
        self._running = False
        logger.info("Agent loop stopping")

    def _get_consolidation_lock(self, session_key: str) -> asyncio.Lock:
        lock = self._consolidation_locks.get(session_key)
        if lock is None:
            lock = asyncio.Lock()
            self._consolidation_locks[session_key] = lock
        return lock

    def _prune_consolidation_lock(self, session_key: str, lock: asyncio.Lock) -> None:
        """Drop lock entry if no longer in use."""
        if not lock.locked():
            self._consolidation_locks.pop(session_key, None)

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        return await process_message(
            self,
            msg=msg,
            session_key=session_key,
            on_progress=on_progress,
        )

    async def _consolidate_memory(self, session, archive_all: bool = False, model: str | None = None) -> bool:
        """Delegate to MemoryStore.consolidate(). Returns True on success."""
        return await self.memory_store.consolidate(
            session, self.provider, (model or self.model),
            archive_all=archive_all, memory_window=self.memory_window,
        )

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Process a message directly (for CLI or cron usage)."""
        await self._connect_mcp()
        return await process_direct_message(
            self,
            content=content,
            session_key=session_key,
            channel=channel,
            chat_id=chat_id,
            on_progress=on_progress,
        )
