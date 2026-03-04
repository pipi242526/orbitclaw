"""Agent orchestration facade.

This module centralizes AgentLoop construction so app-layer entry points
can depend on a stable orchestration API instead of wiring loop internals.
"""

from __future__ import annotations

from typing import Any

from lunaeclaw.core.agent.loop import AgentLoop


def build_agent_loop(
    *,
    config: Any,
    bus: Any,
    provider: Any,
    cron_service: Any = None,
    session_manager: Any = None,
) -> AgentLoop:
    """Create AgentLoop from config defaults with backward-compatible wiring."""
    return AgentLoop(
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
        cron_service=cron_service,
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
        reply_language=config.agents.defaults.reply_language,
        auto_reply_fallback_language=config.agents.defaults.auto_reply_fallback_language,
        cross_lingual_search=config.agents.defaults.cross_lingual_search,
        files_hub_exports_dir=config.tools.files_hub.exports_dir,
        max_history_chars=config.agents.defaults.max_history_chars,
        max_memory_context_chars=config.agents.defaults.max_memory_context_chars,
        max_background_context_chars=config.agents.defaults.max_background_context_chars,
        max_inline_image_bytes=config.agents.defaults.max_inline_image_bytes,
        auto_compact_background=config.agents.defaults.auto_compact_background,
        system_prompt_cache_ttl_seconds=config.agents.defaults.system_prompt_cache_ttl_seconds,
        session_cache_max_entries=config.agents.defaults.session_cache_max_entries,
        gc_every_turns=config.agents.defaults.gc_every_turns,
        turn_timeout_seconds=config.agents.defaults.turn_timeout_seconds,
    )

