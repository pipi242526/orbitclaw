from __future__ import annotations

import json
import time

from orbitclaw.gateway.control import write_gateway_runtime_state
from orbitclaw.webui.services import evaluate_gateway_runtime_status


def _make_cfg(tmp_path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text("{}", encoding="utf-8")
    return cfg_path


def test_runtime_guard_ready_when_same_dir_and_fresh(tmp_path):
    cfg_path = _make_cfg(tmp_path)
    write_gateway_runtime_state(cfg_path, fingerprint="x1", status="running", note="ok")
    ready, reason_en, _ = evaluate_gateway_runtime_status(cfg_path)
    assert ready is True
    assert reason_en == "ok"


def test_runtime_guard_not_ready_when_state_missing(tmp_path):
    cfg_path = _make_cfg(tmp_path)
    ready, reason_en, _ = evaluate_gateway_runtime_status(cfg_path)
    assert ready is False
    assert "no gateway runtime state" in reason_en


def test_runtime_guard_not_ready_when_data_dir_mismatch(tmp_path):
    cfg_path = _make_cfg(tmp_path)
    other_cfg = tmp_path / "other" / "config.json"
    other_cfg.parent.mkdir(parents=True, exist_ok=True)
    other_cfg.write_text("{}", encoding="utf-8")
    write_gateway_runtime_state(other_cfg, fingerprint="x1", status="running", note="ok")
    state_file = other_cfg.parent / "runtime" / "gateway.state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["dataDir"] = str(cfg_path.parent.resolve())
    state_file.write_text(json.dumps(state), encoding="utf-8")
    ready, reason_en, _ = evaluate_gateway_runtime_status(other_cfg)
    assert ready is False
    assert "data directory mismatch" in reason_en


def test_runtime_guard_not_ready_when_stale(tmp_path):
    cfg_path = _make_cfg(tmp_path)
    write_gateway_runtime_state(cfg_path, fingerprint="x1", status="running", note="ok")
    state_file = cfg_path.parent / "runtime" / "gateway.state.json"
    old_ts = time.time() - 600
    state_file.write_text(
        json.dumps(
            {
                "status": "running",
                "fingerprint": "x1",
                "note": "ok",
                "pid": 1,
                "configPath": str(cfg_path.resolve()),
                "dataDir": str(cfg_path.parent.resolve()),
                "updatedAt": old_ts,
            }
        ),
        encoding="utf-8",
    )
    ready, reason_en, _ = evaluate_gateway_runtime_status(cfg_path)
    assert ready is False
    assert "not alive" in reason_en


def test_webui_post_actions_importable():
    import orbitclaw.webui.post_actions as post_actions

    assert hasattr(post_actions, "handle_post_endpoints")
