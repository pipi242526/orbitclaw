"""Agent loop: the core processing engine."""

from __future__ import annotations

import asyncio
import gc
import json
import re
from contextlib import AsyncExitStack
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from loguru import logger

from nanobot.agent.context import ContextBuilder
from nanobot.agent.memory import MemoryStore
from nanobot.agent.subagent import SubagentManager
from nanobot.agent.tools.cron import CronTool
from nanobot.agent.tools.alias import install_tool_aliases
from nanobot.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from nanobot.agent.tools.message import MessageTool
from nanobot.agent.tools.registry import ToolRegistry
from nanobot.agent.tools.shell import ExecTool
from nanobot.agent.tools.spawn import SpawnTool
from nanobot.agent.tools.web import (
    WebFetchTool,
    WebSearchTool,
    has_exa_search_mcp,
    install_exa_web_search_alias,
)
from nanobot.bus.events import InboundMessage, OutboundMessage
from nanobot.bus.queue import MessageBus
from nanobot.providers.base import LLMProvider
from nanobot.session.manager import Session, SessionManager

if TYPE_CHECKING:
    from nanobot.config.schema import ExecToolConfig
    from nanobot.cron.service import CronService


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
        brave_api_key: str | None = None,
        exec_config: ExecToolConfig | None = None,
        cron_service: CronService | None = None,
        restrict_to_workspace: bool = False,
        session_manager: SessionManager | None = None,
        mcp_servers: dict | None = None,
        web_search_provider: str = "auto",
        mcp_enabled_servers: list[str] | None = None,
        mcp_disabled_servers: list[str] | None = None,
        mcp_enabled_tools: list[str] | None = None,
        mcp_disabled_tools: list[str] | None = None,
        tool_aliases: dict[str, str] | None = None,
        enabled_tools: list[str] | None = None,
        disabled_skills: list[str] | None = None,
    ):
        from nanobot.config.schema import ExecToolConfig
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.brave_api_key = brave_api_key
        self.exec_config = exec_config or ExecToolConfig()
        self.cron_service = cron_service
        self.restrict_to_workspace = restrict_to_workspace
        self.enabled_tools = {t.lower() for t in (enabled_tools or [])}
        self.disabled_skills = {s.lower() for s in (disabled_skills or [])}
        self.web_search_provider = self._normalize_web_search_provider(web_search_provider)
        self.tool_aliases = {
            str(k).strip(): str(v).strip()
            for k, v in (tool_aliases or {}).items()
            if str(k).strip() and str(v).strip()
        }

        self.context = ContextBuilder(workspace, disabled_skills=self.disabled_skills)
        self.sessions = session_manager or SessionManager(workspace)
        self.tools = ToolRegistry()
        self._mcp_servers = mcp_servers or {}
        self._mcp_enabled_servers = {s.lower() for s in (mcp_enabled_servers or [])}
        self._mcp_disabled_servers = {s.lower() for s in (mcp_disabled_servers or [])}
        self._mcp_enabled_tools = {s.lower() for s in (mcp_enabled_tools or [])}
        self._mcp_disabled_tools = {s.lower() for s in (mcp_disabled_tools or [])}
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
            brave_api_key=brave_api_key,
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
        )

        self._running = False
        self._mcp_stack: AsyncExitStack | None = None
        self._mcp_connected = False
        self._mcp_connecting = False
        self._consolidating: set[str] = set()  # Session keys with consolidation in progress
        self._consolidation_tasks: set[asyncio.Task] = set()  # Strong refs to in-flight tasks
        self._consolidation_locks: dict[str, asyncio.Lock] = {}
        self._processed_turns = 0
        self._register_default_tools()

    def _tool_enabled(self, name: str) -> bool:
        """Return True if tool is enabled by config (empty list means allow all)."""
        return not self.enabled_tools or name.lower() in self.enabled_tools

    def _mcp_server_enabled(self, name: str) -> bool:
        lname = str(name).lower()
        if self._mcp_enabled_servers and lname not in self._mcp_enabled_servers:
            return False
        if lname in self._mcp_disabled_servers:
            return False
        return True

    @staticmethod
    def _normalize_web_search_provider(value: str | None) -> str:
        mode = (value or "auto").strip().lower()
        return mode if mode in {"auto", "brave", "exa_mcp", "disabled"} else "auto"

    def _should_try_exa_mcp_search(self) -> bool:
        if self.web_search_provider == "disabled":
            return False
        if self.web_search_provider == "brave":
            return False
        return self._exa_mcp_configured

    def _should_allow_brave_web_search(self) -> bool:
        return self.web_search_provider in {"auto", "brave"}

    def _register_default_tools(self) -> None:
        """Register the default set of tools."""
        allowed_dir = self.workspace if self.restrict_to_workspace else None
        file_tools = (
            ("read_file", ReadFileTool),
            ("write_file", WriteFileTool),
            ("edit_file", EditFileTool),
            ("list_dir", ListDirTool),
        )
        for name, cls in file_tools:
            if self._tool_enabled(name):
                self.tools.register(cls(workspace=self.workspace, allowed_dir=allowed_dir))

        if self._tool_enabled("exec"):
            self.tools.register(ExecTool(
                working_dir=str(self.workspace),
                timeout=self.exec_config.timeout,
                restrict_to_workspace=self.restrict_to_workspace,
            ))

        if self._tool_enabled("web_search"):
            self._register_web_search_tool_initial()

        if self._tool_enabled("web_fetch"):
            self.tools.register(WebFetchTool())
        if self._tool_enabled("message"):
            self.tools.register(MessageTool(send_callback=self.bus.publish_outbound))
        if self._tool_enabled("spawn"):
            self.tools.register(SpawnTool(manager=self.subagents))
        if self.cron_service and self._tool_enabled("cron"):
            self.tools.register(CronTool(self.cron_service))
        self._apply_configured_tool_aliases(stage="startup")

    def _register_web_search_tool_initial(self) -> None:
        if not self._tool_enabled("web_search"):
            return
        if self.web_search_provider == "disabled":
            logger.info("web_search provider is disabled; skipping web_search tool registration")
            return
        if self.web_search_provider == "exa_mcp" and not self._exa_mcp_configured:
            logger.warning("web_search provider is exa_mcp but no Exa MCP server is configured; web_search unavailable")
            return
        if self._prefer_exa_mcp_web_search:
            logger.info("Exa MCP detected; deferring built-in web_search registration until MCP connects")
            return
        self._register_brave_web_search_fallback()

    def _register_brave_web_search_fallback(self) -> None:
        if not self._tool_enabled("web_search"):
            return
        if not self._should_allow_brave_web_search():
            return
        if self.tools.has("web_search"):
            return
        if self.brave_api_key:
            self.tools.register(WebSearchTool(api_key=self.brave_api_key))
            logger.info("Registered built-in web_search (Brave Search API)")
            return
        logger.warning("web_search is enabled but tools.web.search.api_key is missing; skipping tool registration")

    def _install_exa_web_search_alias_if_available(self) -> bool:
        if not self._tool_enabled("web_search"):
            return False
        wrapped = install_exa_web_search_alias(self.tools)
        if not wrapped:
            return False
        logger.info("Registered web_search compatibility alias -> {}", wrapped)
        return True

    def _apply_configured_tool_aliases(self, stage: str) -> None:
        if not self.tool_aliases:
            return
        summary = install_tool_aliases(self.tools, self.tool_aliases)
        if summary["installed"]:
            logger.info("Configured tool aliases applied ({}): {}", stage, ", ".join(summary["installed"]))
        if summary["unresolved"]:
            logger.debug("Configured tool aliases unresolved ({}): {}", stage, ", ".join(summary["unresolved"]))

    async def _connect_mcp(self) -> None:
        """Connect to configured MCP servers (one-time, lazy)."""
        if self._mcp_connected or self._mcp_connecting or not self._mcp_servers:
            return
        self._mcp_connecting = True
        from nanobot.agent.tools.mcp import connect_mcp_servers
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
                    if self.web_search_provider == "auto":
                        self._register_brave_web_search_fallback()
            self._apply_configured_tool_aliases(stage="mcp")
            self._mcp_connected = True
        except Exception as e:
            logger.error("Failed to connect MCP servers (will retry next message): {}", e)
            if self._prefer_exa_mcp_web_search and self.web_search_provider == "auto":
                self._register_brave_web_search_fallback()
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

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""
        def _fmt(tc):
            val = next(iter(tc.arguments.values()), None) if tc.arguments else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'
        return ", ".join(_fmt(tc) for tc in tool_calls)

    @staticmethod
    def _processing_notice_text() -> str:
        return "处理中，请稍候…"

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
        """Keep tool outputs bounded to reduce context/token blowup in long runs."""
        if not isinstance(result, str):
            return result
        limit = self._TOOL_RESULT_MAX_CHARS
        if len(result) <= limit:
            return result
        head = result[:limit]
        tail_note = (
            f"\n\n[truncated by nanobot: {len(result) - limit} chars omitted from `{tool_name}` output "
            "to control context size. Ask for a narrower query/file/section if needed.]"
        )
        return head + tail_note

    def _format_user_error(self, err: Exception) -> str:
        """Return a user-facing failure message with reason and likely fixes."""
        raw = str(err).strip() or err.__class__.__name__
        reason = raw
        fixes: list[str] = []
        lower = raw.lower()

        if "tool '" in lower and "not found" in lower:
            fixes.extend([
                "检查 tools.enabled 是否把该工具禁用了",
                "检查 tools.aliases 是否映射到不存在的目标工具",
                "检查 MCP server/tool 过滤项（mcpEnabled*/mcpDisabled*）是否把工具过滤掉了",
            ])
        elif "brave_api_key" in lower or "brave" in lower and "api" in lower:
            fixes.extend([
                "改用 Exa MCP：tools.web.search.provider = exa_mcp（推荐）",
                "或在 tools.web.search.apiKey 配置 Brave Search API key",
            ])
        elif "mcp" in lower and "timed out" in lower:
            fixes.extend([
                "检查对应 MCP 服务是否可用（命令/网络）",
                "适当增大 tools.mcpServers.<name>.toolTimeout",
                "先缩小请求范围（更短网页/更小文件/更精确查询）",
            ])
        elif "no module named" in lower:
            fixes.extend([
                "安装缺失的 Python 依赖后重试",
                "如果是可选功能依赖，先禁用对应工具/技能",
            ])
        elif "timeout" in lower:
            fixes.extend([
                "缩小任务范围后重试",
                "检查网络和目标服务状态",
            ])
        else:
            fixes.extend([
                "运行 `nanobot doctor` 查看工具/技能依赖和配置问题",
                "检查 MCP 配置、API Key、模型名是否正确",
            ])

        lines = [
            "处理失败。",
            f"原因: {reason}",
            "建议:",
        ]
        lines.extend(f"{i}. {fix}" for i, fix in enumerate(fixes, 1))
        return "\n".join(lines)

    def _maybe_release_memory(self, active_session_key: str | None = None) -> None:
        """Periodic lightweight cleanup for long-running gateway processes."""
        self._processed_turns += 1
        keep = {active_session_key} if active_session_key else None
        try:
            self.sessions.prune_cache(keep_keys=keep)
        except Exception:
            logger.debug("Session cache prune skipped")
        if self._processed_turns % self._GC_EVERY_TURNS == 0:
            gc.collect()

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[[str], Awaitable[None]] | None = None,
        model: str | None = None,
    ) -> tuple[str | None, list[str]]:
        """Run the agent iteration loop. Returns (final_content, tools_used)."""
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []
        active_model = model or self.model

        while iteration < self.max_iterations:
            iteration += 1

            response = await self.provider.chat(
                messages=messages,
                tools=self.tools.get_definitions(),
                model=active_model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            if response.has_tool_calls:
                if on_progress:
                    clean = self._strip_think(response.content)
                    if clean:
                        await on_progress(clean)
                    else:
                        await on_progress(self._tool_hint(response.tool_calls))

                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                        }
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages, response.content, tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    args_str = json.dumps(tool_call.arguments, ensure_ascii=False)
                    logger.info("Tool call: {}({})", tool_call.name, args_str[:200])
                    result = await self.tools.execute(tool_call.name, tool_call.arguments)
                    result = self._truncate_tool_result(result, tool_call.name)
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                final_content = self._strip_think(response.content)
                break

        return final_content, tools_used

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
                try:
                    response = await self._process_message(msg)
                    if response is not None:
                        await self.bus.publish_outbound(response)
                    elif msg.channel == "cli":
                        await self.bus.publish_outbound(OutboundMessage(
                            channel=msg.channel, chat_id=msg.chat_id, content="", metadata=msg.metadata or {},
                        ))
                except Exception as e:
                    logger.error("Error processing message: {}", e)
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=self._format_user_error(e)
                    ))
                finally:
                    self._maybe_release_memory(active_session_key=msg.session_key)
            except asyncio.TimeoutError:
                continue

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
        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (msg.chat_id.split(":", 1) if ":" in msg.chat_id
                                else ("cli", msg.chat_id))
            logger.info("Processing system message from {}", msg.sender_id)
            key = f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            self._set_tool_context(channel, chat_id, msg.metadata.get("message_id"))
            messages = self.context.build_messages(
                history=session.get_history(max_messages=self.memory_window),
                current_message=msg.content, channel=channel, chat_id=chat_id,
            )
            final_content, _ = await self._run_agent_loop(messages)
            session.add_message("user", f"[System: {msg.sender_id}] {msg.content}")
            session.add_message("assistant", final_content or "Background task completed.")
            self.sessions.save(session)
            return OutboundMessage(channel=channel, chat_id=chat_id,
                                  content=final_content or "Background task completed.")

        preview = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        logger.info("Processing message from {}:{}: {}", msg.channel, msg.sender_id, preview)

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)

        # Slash commands
        cmd_text = msg.content.strip()
        cmd = cmd_text.lower()
        if cmd == "/new":
            lock = self._get_consolidation_lock(session.key)
            self._consolidating.add(session.key)
            try:
                async with lock:
                    snapshot = session.messages[session.last_consolidated:]
                    if snapshot:
                        temp = Session(key=session.key)
                        temp.messages = list(snapshot)
                        if not await self._consolidate_memory(
                            temp,
                            archive_all=True,
                            model=self._effective_model_for_session(session),
                        ):
                            return OutboundMessage(
                                channel=msg.channel, chat_id=msg.chat_id,
                                content="Memory archival failed, session not cleared. Please try again.",
                            )
            except Exception:
                logger.exception("/new archival failed for {}", session.key)
                return OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content="Memory archival failed, session not cleared. Please try again.",
                )
            finally:
                self._consolidating.discard(session.key)
                self._prune_consolidation_lock(session.key, lock)

            session.clear()
            self.sessions.save(session)
            self.sessions.invalidate(session.key)
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="New session started.")
        if cmd == "/help":
            return OutboundMessage(channel=msg.channel, chat_id=msg.chat_id,
                                  content="🐈 nanobot commands:\n/new — Start a new conversation\n/model — Show or switch model for this session\n/help — Show available commands")

        if cmd == "/model" or cmd.startswith("/model "):
            current_model = self._effective_model_for_session(session)
            arg = cmd_text[6:].strip() if len(cmd_text) >= 6 else ""
            if not arg:
                source = "session override" if session.metadata.get("model_override") else "default"
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=(
                        "当前模型设置\n"
                        f"- 生效模型: `{current_model}` ({source})\n"
                        f"- 默认模型: `{self.model}`\n\n"
                        "用法:\n"
                        "- `/model provider/model-name` 切换当前会话模型\n"
                        "- `/model reset` 恢复默认模型"
                    ),
                )
            if arg.lower() in {"reset", "default"}:
                session.metadata.pop("model_override", None)
                self.sessions.save(session)
                return OutboundMessage(
                    channel=msg.channel, chat_id=msg.chat_id,
                    content=f"已恢复默认模型: `{self.model}`",
                )
            session.metadata["model_override"] = arg
            self.sessions.save(session)
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id,
                content=f"当前会话模型已切换为: `{arg}`\n提示: 仅影响当前会话（{session.key}）。",
            )

        unconsolidated = len(session.messages) - session.last_consolidated
        if (unconsolidated >= self.memory_window and session.key not in self._consolidating):
            self._consolidating.add(session.key)
            lock = self._get_consolidation_lock(session.key)

            async def _consolidate_and_unlock():
                try:
                    async with lock:
                        await self._consolidate_memory(
                            session,
                            model=self._effective_model_for_session(session),
                        )
                finally:
                    self._consolidating.discard(session.key)
                    self._prune_consolidation_lock(session.key, lock)
                    _task = asyncio.current_task()
                    if _task is not None:
                        self._consolidation_tasks.discard(_task)

            _task = asyncio.create_task(_consolidate_and_unlock())
            self._consolidation_tasks.add(_task)

        self._set_tool_context(msg.channel, msg.chat_id, msg.metadata.get("message_id"))
        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool):
                message_tool.start_turn()

        initial_messages = self.context.build_messages(
            history=session.get_history(max_messages=self.memory_window),
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel, chat_id=msg.chat_id,
        )
        effective_model = self._effective_model_for_session(session)
        self.subagents.model = effective_model

        async def _bus_progress(content: str) -> None:
            if msg.channel != "cli":
                return
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            await self.bus.publish_outbound(OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content=content, metadata=meta,
            ))

        processing_notice_task: asyncio.Task | None = None
        if on_progress is None and msg.channel != "cli":
            async def _delayed_notice() -> None:
                try:
                    await asyncio.sleep(self._processing_notice_delay_for_channel(msg.channel))
                    meta = dict(msg.metadata or {})
                    meta["_progress"] = True
                    meta["_progress_kind"] = "processing"
                    await self.bus.publish_outbound(OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=self._processing_notice_text(),
                        metadata=meta,
                    ))
                except asyncio.CancelledError:
                    return
            processing_notice_task = asyncio.create_task(_delayed_notice())

        try:
            final_content, tools_used = await self._run_agent_loop(
                initial_messages, on_progress=on_progress or _bus_progress, model=effective_model,
            )
        finally:
            if processing_notice_task and not processing_notice_task.done():
                processing_notice_task.cancel()
                try:
                    await processing_notice_task
                except asyncio.CancelledError:
                    pass

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        preview = final_content[:120] + "..." if len(final_content) > 120 else final_content
        logger.info("Response to {}:{}: {}", msg.channel, msg.sender_id, preview)

        session.add_message("user", msg.content)
        session.add_message("assistant", final_content,
                            tools_used=tools_used if tools_used else None)
        self.sessions.save(session)

        if message_tool := self.tools.get("message"):
            if isinstance(message_tool, MessageTool) and message_tool._sent_in_turn:
                return None

        return OutboundMessage(
            channel=msg.channel, chat_id=msg.chat_id, content=final_content,
            metadata=msg.metadata or {},
        )

    async def _consolidate_memory(self, session, archive_all: bool = False, model: str | None = None) -> bool:
        """Delegate to MemoryStore.consolidate(). Returns True on success."""
        return await MemoryStore(self.workspace).consolidate(
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
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        try:
            response = await self._process_message(msg, session_key=session_key, on_progress=on_progress)
            return response.content if response else ""
        finally:
            self._maybe_release_memory(active_session_key=session_key)
