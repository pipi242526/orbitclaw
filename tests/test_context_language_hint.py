from pathlib import Path

from nanobot.agent.context import ContextBuilder


def test_detect_reply_language_prefers_chinese_for_cjk_text():
    code, rule = ContextBuilder._detect_reply_language("请读取这个pdf并总结")
    assert code == "zh-CN"
    assert "Chinese" in rule


def test_runtime_context_contains_language_hint():
    ctx = ContextBuilder._build_runtime_context("telegram", "123", current_message="帮我看天气")
    assert "Reply Language Hint: zh-CN" in ctx
    assert "Channel: telegram" in ctx
    assert "Chat ID: 123" in ctx

