from nanobot.config.schema import Config
from nanobot.webui.catalog import (
    evaluate_mcp_library_health,
    find_mcp_library_entry,
    install_skill_from_library,
)


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
