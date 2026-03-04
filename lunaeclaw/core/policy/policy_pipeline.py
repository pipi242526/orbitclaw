"""Policy pipeline for final response constraints and user-facing errors."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

from lunaeclaw.core.policy.language_guard import enforce_reply_language

if TYPE_CHECKING:
    from lunaeclaw.core.context.context import ContextBuilder
    from lunaeclaw.platform.providers.base import LLMProvider


class PolicyPipeline:
    """Centralize language/output policy enforcement for agent replies."""
    _BOX_DRAWING_LINE_RE = re.compile(r"^[\s╭╮╰╯│─▄▀█]+$")
    _TOOL_TRACE_LINE_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"^\s*↳\s+"),
        re.compile(r"^\s*🐈\s*lunaeclaw\s*$", re.IGNORECASE),
        re.compile(r"^\s*calling\s+[\w./-]+\s+function\s+with\s+parameters", re.IGNORECASE),
        re.compile(r"^\s*(?:i\s+will|i['’]ll|i\s+am\s+going\s+to)\s+(?:call|use)\s+[\w./-]+\s*(?:tool|function)?", re.IGNORECASE),
        re.compile(r"^\s*(?:我将|我会|我现在会|我准备)(?:调用|使用).*(?:工具|函数|function|tool)?"),
        re.compile(r"^\s*fastmcp\b", re.IGNORECASE),
        re.compile(r"^\s*https?://gofastmcp\.com/?\s*$", re.IGNORECASE),
        re.compile(r"^\s*server:\s+document loader", re.IGNORECASE),
        re.compile(r"^\s*deploy free:\s*", re.IGNORECASE),
    )

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

    @staticmethod
    def _is_chinese(code: str | None) -> bool:
        return (code or "").lower().startswith("zh")

    def _reply_language_for(self, user_message: str | None = None, target_language: str | None = None) -> str:
        if target_language and target_language != "same_as_user":
            return target_language
        if user_message:
            return self.target_reply_language(user_message) or "zh-CN"
        return "zh-CN"

    @classmethod
    def sanitize_user_visible_output(cls, text: str | None) -> str:
        """Drop internal tool invocation traces and noisy MCP banners from final replies."""
        raw = (text or "").strip()
        if not raw:
            return ""
        lines = raw.splitlines()
        kept: list[str] = []
        for line in lines:
            stripped = line.strip()
            if cls._BOX_DRAWING_LINE_RE.match(stripped):
                continue
            if any(p.search(stripped) for p in cls._TOOL_TRACE_LINE_PATTERNS):
                continue
            kept.append(line)
        cleaned = "\n".join(kept).strip()
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned or raw

    def target_reply_language(self, user_message: str) -> str | None:
        return self.context.resolve_reply_language_target(user_message)

    def processing_notice(self, *, user_message: str | None = None, target_language: str | None = None) -> str:
        code = self._reply_language_for(user_message=user_message, target_language=target_language)
        if self._is_chinese(code):
            return "处理中，请稍候…"
        return "Processing, please wait..."

    def localize(
        self,
        *,
        en: str,
        zh_cn: str,
        user_message: str | None = None,
        target_language: str | None = None,
    ) -> str:
        code = self._reply_language_for(user_message=user_message, target_language=target_language)
        return zh_cn if self._is_chinese(code) else en

    def no_response_fallback(self, *, user_message: str | None = None, target_language: str | None = None) -> str:
        return self.localize(
            en="I've completed processing but have no response to provide.",
            zh_cn="处理已完成，但暂无可返回内容。",
            user_message=user_message,
            target_language=target_language,
        )

    def background_task_completed(self, *, user_message: str | None = None) -> str:
        return self.localize(
            en="Background task completed.",
            zh_cn="后台任务已完成。",
            user_message=user_message,
        )

    def memory_archive_failed(self, *, user_message: str | None = None) -> str:
        return self.localize(
            en="Memory archival failed, session was not cleared. Please try again.",
            zh_cn="记忆归档失败（failed），会话未清空，请稍后重试。",
            user_message=user_message,
        )

    def new_session_started(self, *, user_message: str | None = None) -> str:
        return self.localize(
            en="New session started.",
            zh_cn="已开始新会话（new session started）。",
            user_message=user_message,
        )

    def help_text(self, *, user_message: str | None = None) -> str:
        return self.help_text_from_specs(
            command_specs=[
                ("new", "Start a new conversation", "开始新会话"),
                ("model", "Show or switch model for this session", "查看或切换当前会话模型"),
                ("help", "Show available commands", "查看可用命令"),
            ],
            user_message=user_message,
        )

    def help_text_from_specs(
        self,
        *,
        command_specs: list[tuple[str, str, str]],
        user_message: str | None = None,
    ) -> str:
        zh = self.localize(en="en", zh_cn="zh", user_message=user_message) == "zh"
        title = "🐈 lunaeclaw 命令：" if zh else "🐈 lunaeclaw commands:"
        rows = [title]
        for name, en_desc, zh_desc in command_specs:
            rows.append(f"/{name} — {zh_desc if zh else en_desc}")
        return "\n".join(rows)

    def unknown_command_text(self, *, command_name: str, user_message: str | None = None) -> str:
        return self.localize(
            en=f"Unknown command: `/{command_name}`. Use `/help` to list available commands.",
            zh_cn=f"未知命令：`/{command_name}`。可使用 `/help` 查看可用命令。",
            user_message=user_message,
        )

    def model_source_label(self, *, has_override: bool, user_message: str | None = None) -> str:
        if has_override:
            return self.localize(en="session override", zh_cn="会话覆盖", user_message=user_message)
        return self.localize(en="default", zh_cn="默认值", user_message=user_message)

    def model_status_text(
        self,
        *,
        current_model: str,
        default_model: str,
        source: str,
        endpoint_lines: list[str] | None = None,
        user_message: str | None = None,
    ) -> str:
        suffix = ("\n" + "\n".join(endpoint_lines)) if endpoint_lines else ""
        return self.localize(
            en=(
                "Current model settings\n"
                f"- Active model: `{current_model}` ({source})\n"
                f"- Default model: `{default_model}`\n\n"
                "Usage:\n"
                "- `/model provider/model-name` switch model for current session\n"
                "- `/model reset` restore default model"
                f"{suffix}"
            ),
            zh_cn=(
                "当前模型设置\n"
                f"- 生效模型: `{current_model}` ({source})\n"
                f"- 默认模型: `{default_model}`\n\n"
                "用法:\n"
                "- `/model provider/model-name` 切换当前会话模型\n"
                "- `/model reset` 恢复默认模型"
                f"{suffix}"
            ),
            user_message=user_message,
        )

    def model_endpoints_hint_lines(
        self,
        *,
        endpoint_hints: dict[str, list[str]] | None,
        user_message: str | None = None,
        max_endpoints: int = 8,
        max_models_preview: int = 3,
    ) -> list[str]:
        """Render switchable endpoint hints as localized lines for /model."""
        hints = endpoint_hints or {}
        if not hints:
            return []
        zh = self.localize(en="en", zh_cn="zh", user_message=user_message) == "zh"
        lines: list[str] = ["\n可切换端点:" if zh else "\nSwitchable endpoints:"]
        for name, models in list(hints.items())[:max_endpoints]:
            if models:
                preview = ", ".join(f"`{name}/{m}`" for m in models[:max_models_preview])
                if len(models) > max_models_preview:
                    remain = len(models) - max_models_preview
                    more = f" 等 {len(models)} 个" if zh else f" and {remain} more"
                else:
                    more = ""
                lines.append(f"- {name}: {preview}{more}")
            else:
                lines.append(f"- {name}: `{name}/<model>` ({'任意模型名' if zh else 'any model name'})")
        return lines

    def model_reset_text(self, *, default_model: str, user_message: str | None = None) -> str:
        return self.localize(
            en=f"Default model restored: `{default_model}`",
            zh_cn=f"已恢复默认模型: `{default_model}`",
            user_message=user_message,
        )

    def model_switch_failed_text(self, *, detail: str, user_message: str | None = None) -> str:
        return self.localize(
            en=f"Model switch failed: {detail or 'unknown error'}",
            zh_cn=f"模型切换失败: {detail or '未知错误'}",
            user_message=user_message,
        )

    def model_switched_text(
        self,
        *,
        model_ref: str,
        session_key: str,
        routing_detail: str = "",
        user_message: str | None = None,
    ) -> str:
        extra_zh = f"\n路由: {routing_detail}" if routing_detail else ""
        extra_en = f"\nRouting: {routing_detail}" if routing_detail else ""
        return self.localize(
            en=(
                f"Current session model switched to: `{model_ref}`\n"
                f"Note: only affects this session ({session_key}).{extra_en}"
            ),
            zh_cn=(
                f"当前会话模型已切换为: `{model_ref}`\n"
                f"提示: 仅影响当前会话（{session_key}）。{extra_zh}"
            ),
            user_message=user_message,
        )

    async def enforce_final_reply(
        self,
        *,
        user_message: str,
        draft_reply: str,
        model: str | None = None,
    ) -> str:
        sanitized = self.sanitize_user_visible_output(draft_reply)
        rewritten = await enforce_reply_language(
            provider=self.provider,
            user_message=user_message,
            draft_reply=sanitized,
            target_language=self.target_reply_language(user_message),
            model=model or self.default_model,
            max_tokens=self.max_tokens,
            strip_think=self.strip_think,
        )
        return self.sanitize_user_visible_output(rewritten)

    def format_user_error(
        self,
        err: Exception,
        *,
        user_message: str | None = None,
        target_language: str | None = None,
    ) -> str:
        """Return a user-facing failure message with reason and likely fixes."""
        raw = str(err).strip() or err.__class__.__name__
        reason = self.sanitize_user_visible_output(raw).replace("\n", " ").strip()
        fixes: list[str] = []
        reply_lang = self._reply_language_for(user_message=user_message, target_language=target_language)
        zh = self._is_chinese(reply_lang)
        def t(en, zh_cn):
            return (zh_cn if zh else en)
        lower = raw.lower()

        if "tool '" in lower and "not found" in lower:
            fixes.extend([
                t("Check whether the tool is disabled by tools.enabled.", "检查 tools.enabled 是否把该工具禁用了。"),
                t("Check whether tools.aliases points to a missing target tool.", "检查 tools.aliases 是否映射到不存在的目标工具。"),
                t(
                    "Check MCP server/tool filters (mcpEnabled*/mcpDisabled*) for accidental blocking.",
                    "检查 MCP server/tool 过滤项（mcpEnabled*/mcpDisabled*）是否把工具过滤掉了。",
                ),
            ])
        elif "web_search_exa" in lower or ("exa" in lower and "mcp" in lower and "search" in lower):
            fixes.extend([
                t("Use Exa MCP: tools.web.search.provider = exa_mcp.", "使用 Exa MCP：tools.web.search.provider = exa_mcp。"),
                t(
                    "Check tools.mcpServers.exa and mcpEnabledTools includes web_search_exa.",
                    "检查 tools.mcpServers.exa 和 mcpEnabledTools 是否已启用 web_search_exa。",
                ),
            ])
        elif "mcp" in lower and "timed out" in lower:
            fixes.extend([
                t("Check MCP server availability (command/network).", "检查对应 MCP 服务是否可用（命令/网络）。"),
                t("Increase tools.mcpServers.<name>.toolTimeout.", "适当增大 tools.mcpServers.<name>.toolTimeout。"),
                t(
                    "Reduce request scope first (shorter page/smaller file/more specific query).",
                    "先缩小请求范围（更短网页/更小文件/更精确查询）。",
                ),
            ])
        elif "no module named" in lower:
            fixes.extend([
                t("Install missing Python dependencies and retry.", "安装缺失的 Python 依赖后重试。"),
                t(
                    "If the dependency is optional, disable related tool/skill first.",
                    "如果是可选功能依赖，先禁用对应工具/技能。",
                ),
            ])
        elif "timeout" in lower:
            fixes.extend([
                t("Retry with a smaller task scope.", "缩小任务范围后重试。"),
                t("Check network and target service status.", "检查网络和目标服务状态。"),
            ])
        else:
            fixes.extend([
                t(
                    "Run `lunaeclaw doctor` to inspect tool/skill dependency and config issues.",
                    "运行 `lunaeclaw doctor` 查看工具/技能依赖和配置问题。",
                ),
                t("Check MCP config, API keys, and model names.", "检查 MCP 配置、API Key、模型名是否正确。"),
            ])

        lines = [
            t("Request failed.", "处理失败。"),
            f"{t('Reason', '原因')}: {reason}",
            f"{t('Suggestions', '建议')}:",
        ]
        lines.extend(f"{i}. {fix}" for i, fix in enumerate(fixes, 1))
        return "\n".join(lines)
