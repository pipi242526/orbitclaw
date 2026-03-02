from __future__ import annotations

from pathlib import Path

from orbitclaw.webui.services import (
    configure_runtime_trend_store,
    get_runtime_trend,
    record_runtime_trend_sample,
    runtime_trend_persist_hours_from_env,
)


def test_runtime_trend_env_hours_parsing(monkeypatch):
    monkeypatch.delenv("ORBITCLAW_WEBUI_TREND_PERSIST_HOURS", raising=False)
    assert runtime_trend_persist_hours_from_env() == 0

    monkeypatch.setenv("ORBITCLAW_WEBUI_TREND_PERSIST_HOURS", "24")
    assert runtime_trend_persist_hours_from_env() == 24

    monkeypatch.setenv("ORBITCLAW_WEBUI_TREND_PERSIST_HOURS", "-3")
    assert runtime_trend_persist_hours_from_env() == 0

    monkeypatch.setenv("ORBITCLAW_WEBUI_TREND_PERSIST_HOURS", "x")
    assert runtime_trend_persist_hours_from_env() == 0


def test_runtime_trend_persist_and_reload(tmp_path: Path):
    config_dir = tmp_path / "orbitclaw-home"
    config_dir.mkdir(parents=True, exist_ok=True)

    configure_runtime_trend_store(config_dir, persist_hours=24)
    record_runtime_trend_sample({"mem_used_percent": 48.0, "load1": 0.2, "disk_used_percent": 33.0})
    record_runtime_trend_sample({"mem_used_percent": 49.0, "load1": 0.3, "disk_used_percent": 33.1})

    trend_file = config_dir / "webui.runtime-trend.jsonl"
    assert trend_file.exists()
    lines = [ln for ln in trend_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) >= 2

    # Simulate restart: reconfigure should reload persisted samples.
    configure_runtime_trend_store(config_dir, persist_hours=24)
    rows = get_runtime_trend(limit=10)
    assert rows
    assert any((row.get("mem_used_percent") or 0) >= 48.0 for row in rows)

    # Cleanup global state for other tests.
    configure_runtime_trend_store(config_dir, persist_hours=0)


def test_runtime_trend_memory_only_mode(tmp_path: Path):
    config_dir = tmp_path / "orbitclaw-home"
    config_dir.mkdir(parents=True, exist_ok=True)

    configure_runtime_trend_store(config_dir, persist_hours=0)
    record_runtime_trend_sample({"mem_used_percent": 50.0, "load1": 0.5, "disk_used_percent": 34.0})

    rows = get_runtime_trend(limit=5)
    assert rows
    assert not (config_dir / "webui.runtime-trend.jsonl").exists()

    configure_runtime_trend_store(config_dir, persist_hours=0)
