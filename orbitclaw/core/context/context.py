"""Context builder for assembling agent prompts."""

import re
import time
from pathlib import Path
from typing import Any

from orbitclaw.core.context.memory import MemoryStore
from orbitclaw.core.context.message_payload import (
    append_runtime_context as _append_runtime_context_impl,
)
from orbitclaw.core.context.message_payload import (
    build_user_content as _build_user_content_impl,
)
from orbitclaw.core.context.message_payload import (
    estimate_message_chars as _estimate_message_chars_impl,
)
from orbitclaw.core.context.message_payload import (
    trim_history_by_chars as _trim_history_by_chars_impl,
)
from orbitclaw.core.context.runtime_hints import (
    build_runtime_context as _build_runtime_context_impl,
)
from orbitclaw.core.context.runtime_hints import (
    build_runtime_summary as _build_runtime_summary_impl,
)
from orbitclaw.core.context.runtime_hints import (
    detect_reply_language as _detect_reply_language_impl,
)
from orbitclaw.core.context.runtime_hints import (
    detect_runtime_environment as _detect_runtime_environment_impl,
)
from orbitclaw.core.context.runtime_hints import (
    detect_search_locale_hint as _detect_search_locale_hint_impl,
)
from orbitclaw.core.context.runtime_hints import (
    normalize_language_code as _normalize_language_code_impl,
)
from orbitclaw.core.context.skills import SkillsLoader


class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.

    Assembles bootstrap files, memory, skills, and conversation history
    into a coherent prompt for the LLM.
    """

    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]
    _DEFAULT_MAX_HISTORY_CHARS = 32000
    _DEFAULT_MAX_MEMORY_CONTEXT_CHARS = 12000
    _DEFAULT_MAX_BACKGROUND_CONTEXT_CHARS = 22000
    _DEFAULT_MAX_INLINE_IMAGE_BYTES = 400000
    _DEFAULT_SYSTEM_PROMPT_CACHE_TTL_SECONDS = 20

    def __init__(
        self,
        workspace: Path,
        disabled_skills: set[str] | None = None,
        reply_language_preference: str = "auto",
        auto_reply_fallback_language: str = "zh-CN",
        cross_lingual_search: bool = True,
        max_history_chars: int = _DEFAULT_MAX_HISTORY_CHARS,
        max_memory_context_chars: int = _DEFAULT_MAX_MEMORY_CONTEXT_CHARS,
        max_background_context_chars: int = _DEFAULT_MAX_BACKGROUND_CONTEXT_CHARS,
        max_inline_image_bytes: int = _DEFAULT_MAX_INLINE_IMAGE_BYTES,
        auto_compact_background: bool = True,
        system_prompt_cache_ttl_seconds: int = _DEFAULT_SYSTEM_PROMPT_CACHE_TTL_SECONDS,
    ):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace, disabled_skills=disabled_skills)
        self.reply_language_preference = (reply_language_preference or "auto").strip() or "auto"
        self.auto_reply_fallback_language = self._normalize_language_code(auto_reply_fallback_language)
        self.cross_lingual_search = bool(cross_lingual_search)
        self.max_history_chars = max(0, int(max_history_chars or 0))
        self.max_memory_context_chars = max(0, int(max_memory_context_chars or 0))
        self.max_background_context_chars = max(0, int(max_background_context_chars or 0))
        self.max_inline_image_bytes = max(0, int(max_inline_image_bytes or 0))
        self.auto_compact_background = bool(auto_compact_background)
        self.system_prompt_cache_ttl_seconds = max(0, int(system_prompt_cache_ttl_seconds or 0))
        self._cached_system_prompt_key: tuple[str, ...] | None = None
        self._cached_system_prompt_text: str | None = None
        self._cached_system_prompt_ts: float = 0.0

    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """
        Build the system prompt from bootstrap files, memory, and skills.

        Args:
            skill_names: Optional list of skills to include.

        Returns:
            Complete system prompt.
        """
        cache_key = tuple(sorted((skill_names or [])))
        if (
            self.system_prompt_cache_ttl_seconds > 0
            and self._cached_system_prompt_key == cache_key
            and self._cached_system_prompt_text is not None
            and (time.monotonic() - self._cached_system_prompt_ts) <= self.system_prompt_cache_ttl_seconds
        ):
            return self._cached_system_prompt_text

        parts = []

        # Core identity
        parts.append(self._get_identity())

        # Bootstrap files
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(
                self._compact_background_text(
                    bootstrap,
                    self.max_background_context_chars,
                    label="bootstrap context",
                )
            )

        # Memory context
        memory = self._truncate_text_for_budget(
            self.memory.get_memory_context(),
            self.max_memory_context_chars,
            label="MEMORY context",
        )
        if memory:
            parts.append(f"# Memory\n\n{memory}")

        # Skills - progressive loading
        # 1. Always-loaded skills: include full content
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(
                    self._compact_background_text(
                        f"# Active Skills\n\n{always_content}",
                        max(0, self.max_background_context_chars // 2),
                        label="active skills context",
                    )
                )

        # 2. Available skills: only show summary (agent uses read_file to load)
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(self._compact_background_text(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""",
                    max(0, self.max_background_context_chars // 2),
                    label="skills summary context",
                ))

        prompt = "\n\n---\n\n".join(parts)
        if self.system_prompt_cache_ttl_seconds > 0:
            self._cached_system_prompt_key = cache_key
            self._cached_system_prompt_text = prompt
            self._cached_system_prompt_ts = time.monotonic()
        return prompt

    @staticmethod
    def _truncate_text_for_budget(text: str, budget_chars: int, *, label: str) -> str:
        if not text:
            return text
        if budget_chars <= 0 or len(text) <= budget_chars:
            return text
        omitted = len(text) - budget_chars
        tail = f"\n\n[... {label} truncated by orbitclaw: {omitted} chars omitted for token control ...]"
        keep = max(0, budget_chars - len(tail))
        return text[:keep] + tail

    def _compact_background_text(self, text: str, budget_chars: int, *, label: str) -> str:
        if not text:
            return text
        if budget_chars <= 0 or len(text) <= budget_chars:
            return text
        if not self.auto_compact_background:
            return self._truncate_text_for_budget(text, budget_chars, label=label)

        lines = [line.rstrip() for line in text.splitlines()]
        signal_lines: list[str] = []
        seen: set[str] = set()

        def _push(line: str) -> None:
            v = (line or "").strip()
            if not v or v in seen:
                return
            seen.add(v)
            signal_lines.append(v)

        for line in lines:
            s = line.strip()
            if not s:
                continue
            low = s.lower()
            if (
                s.startswith("#")
                or s.startswith("- ")
                or s.startswith("* ")
                or bool(re.match(r"^\d+\.\s", s))
                or "important" in low
                or "must" in low
                or "do not" in low
                or "policy" in low
            ):
                _push(s)

        for line in lines[:8]:
            _push(line)
        for line in lines[-8:]:
            _push(line)

        if not signal_lines:
            return self._truncate_text_for_budget(text, budget_chars, label=label)

        compacted = (
            f"[auto-compacted {label}: reduced from {len(text)} chars]\n"
            + "\n".join(signal_lines)
        )
        return self._truncate_text_for_budget(compacted, budget_chars, label=label)

    def _get_identity(self) -> str:
        """Get the core identity section."""
        workspace_path = str(self.workspace.expanduser().resolve())
        from orbitclaw.platform.utils.helpers import get_global_skills_path
        global_skills_path = str(get_global_skills_path())
        runtime = self._build_runtime_summary()

        return f"""# orbitclaw 🐈

You are orbitclaw, a helpful AI assistant.

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Long-term memory: {workspace_path}/memory/MEMORY.md
- History log: {workspace_path}/memory/HISTORY.md (grep-searchable)
- Custom skills: {workspace_path}/skills/{{skill-name}}/SKILL.md
- Global skills: {global_skills_path}/{{skill-name}}/SKILL.md

IMPORTANT: When responding to direct questions or conversations, reply directly with your text response.
Only use the 'message' tool when you need to send a message to a specific chat channel (like WhatsApp).
For normal conversation, just respond with text - do not call the message tool.

Always be helpful, accurate, and concise.
Do not expose internal tool names, function calls, arguments, or command syntax in user-facing replies.
If a task takes time, send only a generic progress notice in user language (for example: "处理中，请稍候…").
Never output phrases like "Calling ... tool" or raw function-call JSON to users.
Language policy:
- The final user-facing answer MUST follow the user's language (Chinese user => Chinese answer by default).
- Do NOT switch to English just because a tool/MCP returns English output.
- If a tool returns English content, translate/summarize it in the user's language unless the user explicitly asks to keep English.
Search policy (important for accuracy):
- For region/country-specific topics, do not rely on Chinese-only search terms.
- Translate/rewrite the search query into the local language (and often English), run searches with those variants, then summarize the findings in the user's language.
- Example: if the user asks in Chinese about Japan, search using Japanese keywords first (and optionally English), then answer in Chinese.
If you need to use tools, call them directly — never send a preliminary message like "Let me check" without actually calling a tool.
Attachment routing (prefer lightweight tools first):
- Images/screenshots/photos: use `image_read` if available (or model vision if already attached inline)
- PDF/Word/PPT/Excel and other documents: use `doc_read` if available
- Plain text attachments (`txt`, `md`, `log`, `json`, `yaml`, `csv`, `tsv`): prefer built-in `read_file` first
- To inspect or delete downloaded attachments / generated outputs, prefer `files_hub` (`list` then `delete`, `scope=media|exports`)
- To export generated results, use `export_file` and write into `scope=exports` (via files_hub for listing/cleanup)
- Do NOT claim "export succeeded" unless `export_file` returned `ok=true`; in success replies, include the returned `path` (and `size` if available)
- Weather/forecast requests: use `weather` tool first if available (no API key needed)
- Web pages/articles/docs: try `web_fetch` first; only switch to enhanced MCP fetch/browser tools when built-in extraction fails
When remembering something important, write to {workspace_path}/memory/MEMORY.md
To recall past events, grep {workspace_path}/memory/HISTORY.md"""

    @classmethod
    def _build_runtime_summary(cls) -> str:
        """Build a compact runtime summary for system prompt context."""
        return _build_runtime_summary_impl()

    @staticmethod
    def _detect_runtime_environment(
        *,
        override: str | None = None,
        dockerenv_exists: bool | None = None,
        cgroup_text: str | None = None,
    ) -> tuple[str, str]:
        """Detect whether orbitclaw runs in host or container-like environment."""
        return _detect_runtime_environment_impl(
            override=override,
            dockerenv_exists=dockerenv_exists,
            cgroup_text=cgroup_text,
        )

    @staticmethod
    def _normalize_language_code(value: str | None) -> str:
        return _normalize_language_code_impl(value)

    @classmethod
    def _detect_reply_language(
        cls,
        message: str,
        preferred_language: str | None = "auto",
        fallback_language: str | None = "zh-CN",
    ) -> tuple[str, str]:
        """Heuristic language hint for the current user message."""
        return _detect_reply_language_impl(
            message,
            preferred_language=preferred_language,
            fallback_language=fallback_language,
        )

    @staticmethod
    def _detect_search_locale_hint(message: str) -> str | None:
        """Heuristic hint for cross-lingual search based on user topic region."""
        return _detect_search_locale_hint_impl(message)

    @classmethod
    def _build_runtime_context(
        cls,
        channel: str | None,
        chat_id: str | None,
        current_message: str | None = None,
        *,
        reply_language_preference: str = "auto",
        auto_reply_fallback_language: str = "zh-CN",
        cross_lingual_search: bool = True,
    ) -> str:
        """Build dynamic runtime context and attach it to the tail user message."""
        return _build_runtime_context_impl(
            channel,
            chat_id,
            current_message=current_message,
            reply_language_preference=reply_language_preference,
            auto_reply_fallback_language=auto_reply_fallback_language,
            cross_lingual_search=cross_lingual_search,
        )

    def resolve_reply_language_target(self, message: str) -> str | None:
        """Resolve concrete target language for the final reply, or None for same-as-user."""
        lang_code, _ = self._detect_reply_language(
            message or "",
            preferred_language=self.reply_language_preference,
            fallback_language=self.auto_reply_fallback_language,
        )
        if lang_code == "same_as_user":
            return None
        return lang_code

    @staticmethod
    def _append_runtime_context(
        user_content: str | list[dict[str, Any]],
        runtime_context: str,
    ) -> str | list[dict[str, Any]]:
        """Append runtime context at the tail user message for better prompt cache reuse."""
        return _append_runtime_context_impl(user_content, runtime_context)

    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        parts = []

        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        return "\n\n".join(parts) if parts else ""

    @staticmethod
    def _estimate_message_chars(message: dict[str, Any]) -> int:
        return _estimate_message_chars_impl(message)

    def _trim_history_by_chars(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return _trim_history_by_chars_impl(history, limit=self.max_history_chars)

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        skill_names: list[str] | None = None,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Build the complete message list for an LLM call.

        Args:
            history: Previous conversation messages.
            current_message: The new user message.
            skill_names: Optional skills to include.
            media: Optional list of local file paths for images/media.
            channel: Current channel (telegram, feishu, etc.).
            chat_id: Current chat/user ID.

        Returns:
            List of messages including system prompt.
        """
        messages = []

        # System prompt
        system_prompt = self.build_system_prompt(skill_names)
        messages.append({"role": "system", "content": system_prompt})

        # History
        messages.extend(self._trim_history_by_chars(history))

        # Current message (with optional image attachments)
        user_content = self._build_user_content(current_message, media)
        user_content = self._append_runtime_context(
            user_content=user_content,
            runtime_context=self._build_runtime_context(
                channel,
                chat_id,
                current_message=current_message,
                reply_language_preference=self.reply_language_preference,
                auto_reply_fallback_language=self.auto_reply_fallback_language,
                cross_lingual_search=self.cross_lingual_search,
            ),
        )
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """Build user message content with optional base64-encoded images."""
        return _build_user_content_impl(
            text,
            media,
            max_inline_image_bytes=self.max_inline_image_bytes,
        )

    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str
    ) -> list[dict[str, Any]]:
        """
        Add a tool result to the message list.

        Args:
            messages: Current message list.
            tool_call_id: ID of the tool call.
            tool_name: Name of the tool.
            result: Tool execution result.

        Returns:
            Updated message list.
        """
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result
        })
        return messages

    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Add an assistant message to the message list.

        Args:
            messages: Current message list.
            content: Message content.
            tool_calls: Optional tool calls.
            reasoning_content: Thinking output (Kimi, DeepSeek-R1, etc.).

        Returns:
            Updated message list.
        """
        msg: dict[str, Any] = {"role": "assistant"}

        # Always include content — some providers (e.g. StepFun) reject
        # assistant messages that omit the key entirely.
        msg["content"] = content

        if tool_calls:
            msg["tool_calls"] = tool_calls

        # Include reasoning content when provided (required by some thinking models)
        if reasoning_content is not None:
            msg["reasoning_content"] = reasoning_content

        messages.append(msg)
        return messages
