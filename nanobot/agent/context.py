"""Context builder for assembling agent prompts."""

import base64
import mimetypes
import platform
import re
from pathlib import Path
from typing import Any

from nanobot.agent.memory import MemoryStore
from nanobot.agent.skills import SkillsLoader


class ContextBuilder:
    """
    Builds the context (system prompt + messages) for the agent.
    
    Assembles bootstrap files, memory, skills, and conversation history
    into a coherent prompt for the LLM.
    """
    
    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md", "IDENTITY.md"]
    
    def __init__(
        self,
        workspace: Path,
        disabled_skills: set[str] | None = None,
        reply_language_preference: str = "auto",
        cross_lingual_search: bool = True,
    ):
        self.workspace = workspace
        self.memory = MemoryStore(workspace)
        self.skills = SkillsLoader(workspace, disabled_skills=disabled_skills)
        self.reply_language_preference = (reply_language_preference or "auto").strip() or "auto"
        self.cross_lingual_search = bool(cross_lingual_search)
    
    def build_system_prompt(self, skill_names: list[str] | None = None) -> str:
        """
        Build the system prompt from bootstrap files, memory, and skills.
        
        Args:
            skill_names: Optional list of skills to include.
        
        Returns:
            Complete system prompt.
        """
        parts = []
        
        # Core identity
        parts.append(self._get_identity())
        
        # Bootstrap files
        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)
        
        # Memory context
        memory = self.memory.get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")
        
        # Skills - progressive loading
        # 1. Always-loaded skills: include full content
        always_skills = self.skills.get_always_skills()
        if always_skills:
            always_content = self.skills.load_skills_for_context(always_skills)
            if always_content:
                parts.append(f"# Active Skills\n\n{always_content}")
        
        # 2. Available skills: only show summary (agent uses read_file to load)
        skills_summary = self.skills.build_skills_summary()
        if skills_summary:
            parts.append(f"""# Skills

The following skills extend your capabilities. To use a skill, read its SKILL.md file using the read_file tool.
Skills with available="false" need dependencies installed first - you can try installing them with apt/brew.

{skills_summary}""")
        
        return "\n\n---\n\n".join(parts)
    
    def _get_identity(self) -> str:
        """Get the core identity section."""
        workspace_path = str(self.workspace.expanduser().resolve())
        from nanobot.utils.helpers import get_global_skills_path
        global_skills_path = str(get_global_skills_path())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"
        
        return f"""# nanobot 🐈

You are nanobot, a helpful AI assistant. 

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

Always be helpful, accurate, and concise. Before calling tools, briefly tell the user what you're about to do (one short sentence in the user's language).
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
- To inspect or delete downloaded attachments in `~/.nanobot/media`, use `media_files` (`list` then `delete`)
- Weather/forecast requests: use `weather` tool first if available (no API key needed)
- Web pages/articles/docs: try `web_fetch` first; only switch to enhanced MCP fetch/browser tools when built-in extraction fails
When remembering something important, write to {workspace_path}/memory/MEMORY.md
To recall past events, grep {workspace_path}/memory/HISTORY.md"""

    @staticmethod
    @staticmethod
    def _normalize_language_code(value: str | None) -> str:
        raw = (value or "").strip()
        if not raw:
            return "auto"
        lowered = raw.lower()
        aliases = {
            "auto": "auto",
            "zh": "zh-CN",
            "zh-cn": "zh-CN",
            "zh-hans": "zh-CN",
            "cn": "zh-CN",
            "en": "en",
            "en-us": "en",
            "ja": "ja",
            "ja-jp": "ja",
            "jp": "ja",
            "ko": "ko",
            "ko-kr": "ko",
        }
        return aliases.get(lowered, raw)

    @classmethod
    def _detect_reply_language(
        cls,
        message: str,
        preferred_language: str | None = "auto",
    ) -> tuple[str, str]:
        """Heuristic language hint for the current user message."""
        pref = cls._normalize_language_code(preferred_language)
        if pref != "auto":
            return (
                pref,
                f"Final reply MUST be in {pref} unless the user explicitly requests another language.",
            )
        text = (message or "").strip()
        if not text:
            return ("same_as_user", "Reply in the same language as the user.")

        cjk_count = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))
        latin_count = len(re.findall(r"[A-Za-z]", text))
        # Chinese-heavy input: strongly force Simplified Chinese output.
        if cjk_count >= 2 and cjk_count >= latin_count:
            return (
                "zh-CN",
                "The user's message is in Chinese. Final reply MUST be in Simplified Chinese unless they explicitly request another language.",
            )
        if latin_count >= 4 and cjk_count == 0:
            return ("en", "The user's message appears to be English. Final reply should be in English unless they ask otherwise.")
        return ("same_as_user", "Final reply should follow the user's language.")

    @staticmethod
    def _detect_search_locale_hint(message: str) -> str | None:
        """Heuristic hint for cross-lingual search based on user topic region."""
        text = (message or "").strip()
        if not text:
            return None
        # Start small and precise; expand later if needed.
        japan_markers = ("日本", "东京", "大阪", "京都", "札幌", "横滨", "日元", "日经", "日本股市")
        if any(marker in text for marker in japan_markers):
            return (
                "Cross-lingual search hint: topic appears Japan-related. "
                "Prefer Japanese search keywords first (and optionally English), then answer in Chinese."
            )
        return None

    @classmethod
    def _build_runtime_context(
        cls,
        channel: str | None,
        chat_id: str | None,
        current_message: str | None = None,
        *,
        reply_language_preference: str = "auto",
        cross_lingual_search: bool = True,
    ) -> str:
        """Build dynamic runtime context and attach it to the tail user message."""
        from datetime import datetime
        import time as _time

        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = _time.strftime("%Z") or "UTC"
        lines = [f"Current Time: {now} ({tz})"]
        lang_code, lang_rule = cls._detect_reply_language(current_message or "", preferred_language=reply_language_preference)
        lines.append(f"Reply Language Hint: {lang_code}")
        lines.append(f"Reply Language Rule: {lang_rule}")
        search_hint = cls._detect_search_locale_hint(current_message or "") if cross_lingual_search else None
        if search_hint:
            lines.append(f"Search Locale Hint: {search_hint}")
        if channel and chat_id:
            lines.append(f"Channel: {channel}")
            lines.append(f"Chat ID: {chat_id}")
        return "\n".join(lines)

    @staticmethod
    def _append_runtime_context(
        user_content: str | list[dict[str, Any]],
        runtime_context: str,
    ) -> str | list[dict[str, Any]]:
        """Append runtime context at the tail user message for better prompt cache reuse."""
        runtime_block = f"[Runtime Context]\n{runtime_context}"
        if isinstance(user_content, str):
            return f"{user_content}\n\n{runtime_block}"
        content = list(user_content)
        content.append({"type": "text", "text": runtime_block})
        return content
    
    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        parts = []
        
        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")
        
        return "\n\n".join(parts) if parts else ""
    
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
        messages.extend(history)

        # Current message (with optional image attachments)
        user_content = self._build_user_content(current_message, media)
        user_content = self._append_runtime_context(
            user_content=user_content,
            runtime_context=self._build_runtime_context(
                channel,
                chat_id,
                current_message=current_message,
                reply_language_preference=self.reply_language_preference,
                cross_lingual_search=self.cross_lingual_search,
            ),
        )
        messages.append({"role": "user", "content": user_content})

        return messages

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """Build user message content with optional base64-encoded images."""
        if not media:
            return text
        
        images = []
        non_image_attachments: list[str] = []
        for path in media:
            p = Path(path)
            mime, _ = mimetypes.guess_type(path)
            if not p.is_file():
                continue
            if not mime or not mime.startswith("image/"):
                non_image_attachments.append(str(p))
                continue
            b64 = base64.b64encode(p.read_bytes()).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

        attachment_hint = ""
        if non_image_attachments:
            plain_text_exts = {".txt", ".md", ".log", ".json", ".yaml", ".yml", ".csv", ".tsv"}
            plain_text_files = [p for p in non_image_attachments if Path(p).suffix.lower() in plain_text_exts]
            binary_doc_files = [p for p in non_image_attachments if p not in plain_text_files]
            lines = "\n".join(f"- {p}" for p in non_image_attachments)
            hint_lines = []
            if plain_text_files:
                txt_lines = "\n".join(f"  - {p}" for p in plain_text_files)
                hint_lines.append(f"Plain-text files (prefer `read_file`):\n{txt_lines}")
            if binary_doc_files:
                doc_lines = "\n".join(f"  - {p}" for p in binary_doc_files)
                hint_lines.append(f"Document files (prefer `doc_read`):\n{doc_lines}")
            attachment_hint = (
                "\n\nAttached local files (non-image):\n"
                f"{lines}\n"
                + ("\n" + "\n".join(hint_lines) if hint_lines else "")
            )

        if not images:
            return text + attachment_hint
        return images + [{"type": "text", "text": text + attachment_hint}]
    
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
