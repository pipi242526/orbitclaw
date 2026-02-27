import json

from nanobot.config.loader import inspect_config_hints, save_config
from nanobot.config.schema import Config, EndpointProviderConfig


def test_save_config_slims_duplicates_and_legacy_web_search_fields(tmp_path):
    cfg = Config()
    cfg.tools.enabled = ["read_file", "web_search", "web_search"]
    cfg.tools.mcp_enabled_servers = ["exa", "exa", "docloader"]
    cfg.tools.mcp_enabled_tools = ["web_search_exa", "web_search_exa", "read_document"]
    cfg.tools.aliases = {
        "": "x",
        "noop": "noop",
        "web_search": "mcp_exa_web_search_exa",
        " doc_read ": "mcp_docloader_read_document",
    }
    cfg.tools.web.search.provider = "brave"
    cfg.skills.disabled = ["tmux", "tmux", "clawhub"]
    cfg.providers.endpoints = {
        " myopen ": EndpointProviderConfig(
            type="OpenAI-Compatible",
            models=["qwen-max", "qwen-max", "deepseek-v3"],
        )
    }

    out = tmp_path / "config.json"
    save_config(cfg, out)
    data = json.loads(out.read_text(encoding="utf-8"))

    assert data["tools"]["enabled"] == ["read_file", "web_search"]
    assert data["tools"]["mcpEnabledServers"] == ["exa", "docloader"]
    assert data["tools"]["mcpEnabledTools"] == ["web_search_exa", "read_document"]
    assert data["tools"]["aliases"] == {
        "web_search": "mcp_exa_web_search_exa",
        "doc_read": "mcp_docloader_read_document",
    }
    assert data["tools"]["web"]["search"]["provider"] == "exa_mcp"
    assert "apiKey" not in data["tools"]["web"]["search"]
    assert data["skills"]["disabled"] == ["tmux", "clawhub"]
    assert data["providers"]["endpoints"] == {
        "myopen": {
            "type": "openai_compatible",
            "models": ["qwen-max", "deepseek-v3"],
            "enabled": True,
            "apiKey": "",
            "apiBase": None,
            "extraHeaders": None,
        }
    }


def test_inspect_config_hints_reports_legacy_and_duplicates(tmp_path):
    raw = {
        "channels": {"sendToolHints": True},
        "tools": {
            "enabled": ["web_search", "web_search"],
            "aliases": {"foo": "foo"},
            "exec": {"restrictToWorkspace": True},
            "web": {"search": {"provider": "brave"}},
        },
        "providers": {
            "endpoints": {
                "ohmygpt": {"models": ["ohmygpt/gemini-2.5-flash-lite"]},
            }
        },
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    hints = inspect_config_hints(path)
    joined = "\n".join(hints)
    assert "tools.exec.restrictToWorkspace" in joined
    assert "legacy web.search.provider" in joined
    assert "contains duplicates" in joined
    assert "self mapping" in joined
    assert "sendToolHints=true" in joined
    assert "model allowlist uses endpoint prefix" in joined


def test_inspect_config_hints_handles_invalid_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ invalid json", encoding="utf-8")
    hints = inspect_config_hints(path)
    assert hints
    assert "config parse error" in hints[0]
