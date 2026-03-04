from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from orbitclaw.capabilities.tools.registry import ToolRegistry
from orbitclaw.core.agent.loop import AgentLoop
from orbitclaw.core.agent.toolset_builder import ToolsetBuilder
from orbitclaw.core.bus.queue import MessageBus
from orbitclaw.core.context.context import ContextBuilder
from orbitclaw.core.policy.policy_pipeline import PolicyPipeline
from orbitclaw.platform.providers.base import LLMResponse


def test_detect_reply_language_prefers_chinese_for_cjk_text():
    code, rule = ContextBuilder._detect_reply_language("请读取这个pdf并总结")
    assert code == "zh-CN"
    assert "Chinese" in rule


def test_runtime_context_contains_language_hint():
    ctx = ContextBuilder._build_runtime_context("telegram", "123", current_message="帮我看天气")
    assert "Reply Language Hint: zh-CN" in ctx
    assert "Channel: telegram" in ctx
    assert "Chat ID: 123" in ctx


def test_context_resolve_reply_language_target(tmp_path: Path):
    ctx = ContextBuilder(tmp_path, reply_language_preference="ja")
    assert ctx.resolve_reply_language_target("请读取这张图") == "ja"


def test_runtime_context_contains_japan_search_locale_hint():
    ctx = ContextBuilder._build_runtime_context(None, None, current_message="帮我查一下日本AI政策最新消息")
    assert "Search Locale Hint:" in ctx
    assert "Japan-related" in ctx


def test_explicit_reply_language_preference_overrides_detection():
    ctx = ContextBuilder._build_runtime_context(
        None,
        None,
        current_message="请总结这份pdf",
        reply_language_preference="ja",
    )
    assert "Reply Language Hint: ja" in ctx


def test_detect_reply_language_prefers_japanese_when_kana_present():
    code, _ = ContextBuilder._detect_reply_language("日本のAI政策をまとめて")
    assert code == "ja"


def test_detect_reply_language_uses_fallback_when_ambiguous():
    code, _ = ContextBuilder._detect_reply_language("12345 ???", fallback_language="en")
    assert code == "en"


def test_runtime_context_contains_korea_search_locale_hint():
    ctx = ContextBuilder._build_runtime_context(None, None, current_message="帮我查韩国半导体最新政策")
    assert "Search Locale Hint:" in ctx
    assert "Korea-related" in ctx


def test_build_messages_trims_history_by_char_budget(tmp_path: Path):
    ctx = ContextBuilder(tmp_path, max_history_chars=360, system_prompt_cache_ttl_seconds=0)
    history = [
        {"role": "user", "content": "u1 " * 40},
        {"role": "assistant", "content": "a1 " * 40},
        {"role": "user", "content": "u2 " * 40},
        {"role": "assistant", "content": "a2 " * 40},
    ]
    messages = ctx.build_messages(history=history, current_message="new message")
    trimmed_history = messages[1:-1]
    assert len(trimmed_history) == 2
    assert trimmed_history[0]["role"] == "user"
    assert "u2" in trimmed_history[0]["content"]


def test_build_user_content_skips_oversized_inline_image(tmp_path: Path):
    img = tmp_path / "large.png"
    img.write_bytes(b"0" * 64)
    ctx = ContextBuilder(tmp_path, max_inline_image_bytes=10)
    content = ctx._build_user_content("read this", [str(img)])
    assert isinstance(content, str)
    assert "Large images skipped for inline vision" in content
    assert str(img) in content


def test_system_prompt_uses_ttl_cache(tmp_path: Path):
    ctx = ContextBuilder(tmp_path, system_prompt_cache_ttl_seconds=60)
    ctx._load_bootstrap_files = MagicMock(return_value="")
    ctx.memory.get_memory_context = MagicMock(return_value="")
    ctx.skills.get_always_skills = MagicMock(return_value=[])
    ctx.skills.build_skills_summary = MagicMock(return_value="")

    first = ctx.build_system_prompt()
    second = ctx.build_system_prompt()

    assert first == second
    assert ctx._load_bootstrap_files.call_count == 1


def test_compact_background_text_uses_structural_summary(tmp_path: Path):
    ctx = ContextBuilder(
        tmp_path,
        max_background_context_chars=220,
        auto_compact_background=True,
        system_prompt_cache_ttl_seconds=0,
    )
    text = "\n".join(
        [
            "# Title",
            "IMPORTANT: this line should remain",
            "- bullet one",
            "do not skip this policy",
            "plain text " * 40,
        ]
    )
    compacted = ctx._compact_background_text(text, 220, label="test background")
    assert len(compacted) <= 220
    assert "auto-compacted" in compacted
    assert "IMPORTANT" in compacted


def test_detect_runtime_environment_supports_explicit_override():
    kind, hint = ContextBuilder._detect_runtime_environment(override="docker")
    assert kind == "docker"
    assert "ORBITCLAW_RUNTIME_KIND" in hint


def test_detect_runtime_environment_detects_kubernetes_marker():
    kind, hint = ContextBuilder._detect_runtime_environment(
        dockerenv_exists=False,
        cgroup_text="0::/kubepods.slice/pod123",
    )
    assert kind == "kubernetes"
    assert "kubepods" in hint


def test_toolset_builder_registers_shared_core_tools(tmp_path: Path):
    tools = ToolRegistry()
    builder = ToolsetBuilder(
        workspace=tmp_path,
        restrict_to_workspace=False,
        enabled_tools=set(),
        exec_timeout=30,
    )

    builder.register_core_tools(tools)
    names = set(tools.tool_names)

    assert {
        "read_file",
        "write_file",
        "edit_file",
        "list_dir",
        "exec",
        "web_fetch",
        "files_hub",
        "export_file",
        "weather",
    }.issubset(names)
    assert "message" not in names
    assert "spawn" not in names


def test_policy_pipeline_formats_missing_tool_error(tmp_path: Path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    ctx = ContextBuilder(tmp_path)
    pipeline = PolicyPipeline(
        provider=provider,
        context=ctx,
        default_model="test-model",
        max_tokens=1024,
        strip_think=lambda text: text,
    )

    msg = pipeline.format_user_error(RuntimeError("Error: Tool 'doc_read' not found"))
    assert "tools.enabled" in msg
    assert "tools.aliases" in msg


def test_policy_pipeline_sanitizes_tool_trace_lines(tmp_path: Path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    ctx = ContextBuilder(tmp_path)
    pipeline = PolicyPipeline(
        provider=provider,
        context=ctx,
        default_model="test-model",
        max_tokens=1024,
        strip_think=lambda text: text,
    )

    draft = (
        "我将调用 files_hub(action=\"list\")。\n"
        "↳ 现在执行工具\n"
        "Calling doc_read function with parameters: {\"file_path\": \"a.pdf\"}\n"
        "╭──────────────────────────────╮\n"
        "FastMCP 3.0.2\n"
        "https://gofastmcp.com\n"
        "╰──────────────────────────────╯\n"
        "这是最终结果。"
    )
    cleaned = pipeline.sanitize_user_visible_output(draft)
    assert "Calling doc_read function" not in cleaned
    assert "FastMCP 3.0.2" not in cleaned
    assert "这是最终结果。" in cleaned


def test_policy_pipeline_formats_error_in_english_for_english_user(tmp_path: Path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    ctx = ContextBuilder(tmp_path)
    pipeline = PolicyPipeline(
        provider=provider,
        context=ctx,
        default_model="test-model",
        max_tokens=1024,
        strip_think=lambda text: text,
    )

    msg = pipeline.format_user_error(RuntimeError("timeout"), user_message="please check this website")
    assert msg.startswith("Request failed.")
    assert "Suggestions:" in msg


def test_policy_pipeline_processing_notice_follows_user_language(tmp_path: Path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    ctx = ContextBuilder(tmp_path)
    pipeline = PolicyPipeline(
        provider=provider,
        context=ctx,
        default_model="test-model",
        max_tokens=1024,
        strip_think=lambda text: text,
    )

    assert pipeline.processing_notice(user_message="请帮我查天气") == "处理中，请稍候…"
    assert pipeline.processing_notice(user_message="please check weather") == "Processing, please wait..."


def test_policy_pipeline_localize_and_no_response_fallback(tmp_path: Path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    ctx = ContextBuilder(tmp_path)
    pipeline = PolicyPipeline(
        provider=provider,
        context=ctx,
        default_model="test-model",
        max_tokens=1024,
        strip_think=lambda text: text,
    )

    assert pipeline.localize(en="ok", zh_cn="好的", user_message="你好") == "好的"
    assert pipeline.localize(en="ok", zh_cn="好的", user_message="hello") == "ok"
    assert "暂无可返回内容" in pipeline.no_response_fallback(user_message="请继续")


def test_policy_pipeline_command_text_helpers(tmp_path: Path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    ctx = ContextBuilder(tmp_path)
    pipeline = PolicyPipeline(
        provider=provider,
        context=ctx,
        default_model="test-model",
        max_tokens=1024,
        strip_think=lambda text: text,
    )

    assert "new session started" in pipeline.new_session_started(user_message="请重开会话").lower()
    assert "命令" in pipeline.help_text(user_message="请给我帮助")
    assert "Default model restored" in pipeline.model_reset_text(default_model="a/b", user_message="reset")
    assert "未知命令" in pipeline.unknown_command_text(command_name="abc", user_message="请执行")


def test_policy_pipeline_model_endpoints_hint_lines(tmp_path: Path):
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    ctx = ContextBuilder(tmp_path)
    pipeline = PolicyPipeline(
        provider=provider,
        context=ctx,
        default_model="test-model",
        max_tokens=1024,
        strip_think=lambda text: text,
    )

    hints = {
        "ohmygpt": ["gemini-2.5-flash-lite", "gpt-4o-mini", "qwen-plus", "deepseek-v3"],
        "free": [],
    }
    zh_lines = pipeline.model_endpoints_hint_lines(endpoint_hints=hints, user_message="请看模型")
    en_lines = pipeline.model_endpoints_hint_lines(endpoint_hints=hints, user_message="show models")
    assert zh_lines[0].startswith("\n可切换端点")
    assert "任意模型名" in "\n".join(zh_lines)
    assert en_lines[0].startswith("\nSwitchable endpoints")
    assert "any model name" in "\n".join(en_lines)


@pytest.mark.asyncio
async def test_agent_loop_unknown_command_returns_hint(tmp_path: Path):
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    loop = AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model="test-model")

    msg = await loop.process_direct("/not_exist", channel="cli", chat_id="direct")
    assert "/help" in msg


@pytest.mark.asyncio
async def test_reply_language_guard_rewrites_english_draft_for_chinese_user(tmp_path: Path):
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat = AsyncMock(
        return_value=LLMResponse(content="图片里是注册成功提示，并包含绑定链接。", tool_calls=[])
    )
    loop = AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model="test-model")

    draft = "The screenshot shows a successful registration notice and a claim URL."
    rewritten = await loop._enforce_reply_language(
        user_message="请帮我识图并总结",
        draft_reply=draft,
        model="test-model",
    )

    assert "注册成功" in rewritten
    provider.chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_reply_language_guard_skips_code_heavy_reply(tmp_path: Path):
    bus = MessageBus()
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    provider.chat = AsyncMock(return_value=LLMResponse(content="不应被调用", tool_calls=[]))
    loop = AgentLoop(bus=bus, provider=provider, workspace=tmp_path, model="test-model")

    draft = (
        "Use this script:\n"
        "```python\n"
        "def parse_image(path):\n"
        "    return summarize(path)\n"
        "```\n"
        "Run it and check output."
    )
    rewritten = await loop._enforce_reply_language(
        user_message="请看下这张图",
        draft_reply=draft,
        model="test-model",
    )

    assert rewritten == draft
    provider.chat.assert_not_awaited()
