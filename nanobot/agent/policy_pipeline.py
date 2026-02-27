"""Policy pipeline for final response constraints and user-facing errors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from nanobot.agent.language_guard import enforce_reply_language

if TYPE_CHECKING:
    from nanobot.agent.context import ContextBuilder
    from nanobot.providers.base import LLMProvider


class PolicyPipeline:
    """Centralize language/output policy enforcement for agent replies."""

    def __init__(
        self,
        *,
        provider: "LLMProvider",
        context: "ContextBuilder",
        default_model: str,
        max_tokens: int,
        strip_think: Callable[[str | None], str | None],
    ) -> None:
        self.provider = provider
        self.context = context
        self.default_model = default_model
        self.max_tokens = max_tokens
        self.strip_think = strip_think

    def target_reply_language(self, user_message: str) -> str | None:
        return self.context.resolve_reply_language_target(user_message)

    async def enforce_final_reply(
        self,
        *,
        user_message: str,
        draft_reply: str,
        model: str | None = None,
    ) -> str:
        return await enforce_reply_language(
            provider=self.provider,
            user_message=user_message,
            draft_reply=draft_reply,
            target_language=self.target_reply_language(user_message),
            model=model or self.default_model,
            max_tokens=self.max_tokens,
            strip_think=self.strip_think,
        )

    def format_user_error(self, err: Exception) -> str:
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
        elif "web_search_exa" in lower or ("exa" in lower and "mcp" in lower and "search" in lower):
            fixes.extend([
                "使用 Exa MCP：tools.web.search.provider = exa_mcp",
                "检查 tools.mcpServers.exa 和 mcpEnabledTools 是否已启用 web_search_exa",
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
