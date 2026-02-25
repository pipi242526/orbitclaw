import json

from nanobot.config.loader import save_config
from nanobot.config.schema import Config


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
    cfg.tools.web.search.provider = "auto"
    cfg.tools.web.search.api_key = ""
    cfg.skills.disabled = ["tmux", "tmux", "clawhub"]

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
