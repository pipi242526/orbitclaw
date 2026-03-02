from nanobot.config.schema import Config
from nanobot.webui.catalog import (
    evaluate_mcp_library_health,
    find_mcp_library_entry,
    install_skill_from_library,
    library_text,
)
from nanobot.webui.diagnostics import collect_channel_runtime_issues, collect_tool_policy_diagnostics
from nanobot.webui.i18n import normalize_ui_lang, reply_language_label, tr, ui_term


def test_mcp_library_health_not_installed():
    cfg = Config()
    item = find_mcp_library_entry("exa")
    assert item is not None
    health = evaluate_mcp_library_health(cfg, item)
    assert health["status"] == "not_installed"


def test_mcp_library_health_missing_env(monkeypatch):
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    cfg = Config()
    item = find_mcp_library_entry("exa")
    assert item is not None
    cfg.tools.mcp_servers["exa"] = item["config"]
    health = evaluate_mcp_library_health(cfg, item)
    assert health["status"] == "missing_env"
    assert "EXA_API_KEY" in health["hint"]


def test_install_skill_from_library_to_global_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("nanobot.webui.catalog.get_global_skills_path", lambda: tmp_path)

    ok, msg = install_skill_from_library("weather", overwrite=False)
    assert ok, msg
    assert (tmp_path / "weather" / "SKILL.md").exists()

    ok2, msg2 = install_skill_from_library("weather", overwrite=False)
    assert not ok2
    assert "already exists" in msg2

    ok3, msg3 = install_skill_from_library("weather", overwrite=True)
    assert ok3, msg3


def test_i18n_helpers():
    assert normalize_ui_lang("zh") == "zh-CN"
    assert normalize_ui_lang("en") == "en"
    assert reply_language_label("en", "auto") == "auto (follow user message)"
    assert reply_language_label("zh-CN", "auto") == "auto (跟随用户消息)"
    assert tr("zh-CN", "x", "y") == "y"
    assert ui_term("en", "enabled") == "enabled"
    assert ui_term("zh-CN", "enabled") == "已启用"


def test_library_text_localized():
    item = find_mcp_library_entry("docloader")
    assert item is not None
    assert "FastMCP" in library_text(item, "desc", "en")
    assert "FastMCP" in library_text(item, "desc", "zh-CN")
    assert "文档" in library_text(item, "name", "zh-CN")


def test_tool_policy_diagnostics_localized():
    cfg = Config()
    cfg.tools.enabled = ["web_search", "unknown_tool"]
    zh_rows = collect_tool_policy_diagnostics(cfg, ui_lang="zh-CN")
    en_rows = collect_tool_policy_diagnostics(cfg, ui_lang="en")
    assert any("未知内置工具" in row for row in zh_rows)
    assert any("unknown built-in tools" in row for row in en_rows)
    assert any("`message`" in row for row in en_rows)


def test_channel_runtime_issues_localized():
    raw = Config()
    resolved = Config()
    raw.channels.telegram.enabled = True
    raw.channels.telegram.token = "${TELEGRAM_BOT_TOKEN}"
    resolved.channels.telegram.enabled = True
    resolved.channels.telegram.token = ""
    zh_rows = collect_channel_runtime_issues(raw, resolved, ui_lang="zh-CN")
    en_rows = collect_channel_runtime_issues(raw, resolved, ui_lang="en")
    assert any("缺少环境变量" in row for row in zh_rows)
    assert any("missing env" in row for row in en_rows)
