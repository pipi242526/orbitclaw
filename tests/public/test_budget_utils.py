from orbitclaw.platform.config.schema import Config
from orbitclaw.platform.utils.budget import (
    collect_runtime_budget_alerts,
    estimate_tokens_from_chars,
)


def test_estimate_tokens_from_chars_is_coarse_and_stable():
    assert estimate_tokens_from_chars(0) == 0
    assert estimate_tokens_from_chars(300) == 100
    assert estimate_tokens_from_chars(-100) == 0


def test_collect_runtime_budget_alerts_returns_empty_for_default_budget():
    cfg = Config()
    snapshot = {
        "load1": 0.2,
        "load5": 0.2,
        "load15": 0.2,
        "mem_used_percent": 35.0,
        "disk_used_percent": 50.0,
        "cpu_cores": 4,
    }
    alerts = collect_runtime_budget_alerts(cfg, snapshot)
    assert alerts == []


def test_collect_runtime_budget_alerts_flags_oversized_budget_and_host_pressure():
    cfg = Config()
    cfg.agents.defaults.max_history_chars = 70000
    cfg.agents.defaults.max_memory_context_chars = 40000
    cfg.agents.defaults.max_background_context_chars = 40000
    cfg.agents.defaults.max_inline_image_bytes = 2_000_000
    cfg.agents.defaults.gc_every_turns = 0
    cfg.agents.defaults.session_cache_max_entries = 128

    snapshot = {
        "load1": 10.0,
        "load5": 8.0,
        "load15": 6.0,
        "mem_used_percent": 93.0,
        "disk_used_percent": 91.0,
        "cpu_cores": 4,
    }
    alerts = collect_runtime_budget_alerts(cfg, snapshot)
    messages = "\n".join(str(a.get("message")) for a in alerts)
    severities = {str(a.get("severity")) for a in alerts}

    assert "context token budget too high" in messages
    assert "inline image cap is high" in messages
    assert "gcEveryTurns is 0" in messages
    assert "session cache is large" in messages
    assert "host memory usage is very high" in messages
    assert "disk usage is high" in messages
    assert "host CPU load is high" in messages
    assert "error" in severities
    assert "warn" in severities
