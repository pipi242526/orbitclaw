"""Reusable WebUI service helpers."""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from orbitclaw.app.gateway.control import (
    is_gateway_runtime_fresh,
    read_gateway_runtime_state,
)


def safe_positive_int(raw: str | None, *, default: int = 1, minimum: int = 1) -> int:
    try:
        value = int((raw or "").strip())
    except Exception:
        return default
    return value if value >= minimum else default


def evaluate_gateway_runtime_status(cfg_path: Path) -> tuple[bool, str, str]:
    """
    Validate whether WebUI and gateway share the same active runtime directory.

    Returns:
      (ready, reason_en, reason_zh)
    """
    state = read_gateway_runtime_state(cfg_path)
    if not state:
        return (
            False,
            "no gateway runtime state found in this config directory",
            "当前配置目录未发现 gateway 运行状态文件",
        )
    expected_dir = str(cfg_path.expanduser().resolve().parent)
    actual_dir = str(state.get("dataDir") or "").strip()
    if not actual_dir or actual_dir != expected_dir:
        return (
            False,
            "gateway data directory mismatch",
            "gateway 数据目录不一致",
        )
    raw_poll = (os.environ.get("ORBITCLAW_GATEWAY_RELOAD_POLL_SECONDS") or "2.0").strip()
    try:
        poll_seconds = max(0.5, float(raw_poll))
    except ValueError:
        poll_seconds = 2.0
    max_age = max(6.0, poll_seconds * 3.0 + 2.0)
    if not is_gateway_runtime_fresh(state, max_age_seconds=max_age):
        status = str(state.get("status") or "unknown")
        return (
            False,
            f"gateway not alive in this directory (status={status})",
            f"当前目录内 gateway 未在线（status={status}）",
        )
    return (True, "ok", "正常")


_RUNTIME_TREND_MAX_POINTS = 120
_runtime_trend: deque[dict[str, float | None]] = deque(maxlen=_RUNTIME_TREND_MAX_POINTS)
_runtime_trend_lock = threading.Lock()
_runtime_trend_store_path: Path | None = None
_runtime_trend_persist_seconds: float = 0.0
_last_prune_ts: float = 0.0


def runtime_trend_persist_hours_from_env() -> int:
    """Read optional trend persistence window from env (0 disables persistence)."""
    raw = (os.environ.get("ORBITCLAW_WEBUI_TREND_PERSIST_HOURS") or "0").strip()
    try:
        hours = int(raw)
    except ValueError:
        return 0
    return max(0, min(168, hours))


def configure_runtime_trend_store(config_dir: Path, *, persist_hours: int) -> None:
    """Enable/disable trend persistence and prime in-memory samples from disk."""
    global _runtime_trend_store_path
    global _runtime_trend_persist_seconds
    global _last_prune_ts

    with _runtime_trend_lock:
        _runtime_trend_store_path = None
        _runtime_trend_persist_seconds = 0.0
        _last_prune_ts = 0.0
        _runtime_trend.clear()

        if persist_hours <= 0:
            return

        _runtime_trend_store_path = config_dir.expanduser().resolve() / "webui.runtime-trend.jsonl"
        _runtime_trend_persist_seconds = float(persist_hours) * 3600.0
        _runtime_trend_store_path.parent.mkdir(parents=True, exist_ok=True)
        _load_runtime_trend_from_store()


def record_runtime_trend_sample(snapshot: dict[str, Any]) -> None:
    """Append one lightweight runtime sample for dashboard trend rendering."""
    sample = {
        "ts": float(time.time()),
        "mem_used_percent": _safe_float(snapshot.get("mem_used_percent")),
        "load1": _safe_float(snapshot.get("load1")),
        "disk_used_percent": _safe_float(snapshot.get("disk_used_percent")),
    }
    with _runtime_trend_lock:
        _runtime_trend.append(sample)
        _append_runtime_trend_to_store(sample)


def get_runtime_trend(*, limit: int = 24) -> list[dict[str, float | None]]:
    """Return recent runtime samples, oldest first."""
    keep = max(1, int(limit or 1))
    with _runtime_trend_lock:
        return list(_runtime_trend)[-keep:]


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _load_runtime_trend_from_store() -> None:
    if _runtime_trend_store_path is None or _runtime_trend_persist_seconds <= 0:
        return
    if not _runtime_trend_store_path.exists():
        return
    now = time.time()
    cutoff = now - _runtime_trend_persist_seconds
    try:
        lines = _runtime_trend_store_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    kept: list[dict[str, float | None]] = []
    for line in lines:
        try:
            row = json.loads(line)
        except Exception:
            continue
        ts = _safe_float(row.get("ts"))
        if ts is None or ts < cutoff:
            continue
        kept.append(
            {
                "ts": ts,
                "mem_used_percent": _safe_float(row.get("mem_used_percent")),
                "load1": _safe_float(row.get("load1")),
                "disk_used_percent": _safe_float(row.get("disk_used_percent")),
            }
        )
    for row in kept[-_RUNTIME_TREND_MAX_POINTS:]:
        _runtime_trend.append(row)
    _write_runtime_trend_store(kept[-_RUNTIME_TREND_MAX_POINTS:])


def _append_runtime_trend_to_store(sample: dict[str, float | None]) -> None:
    if _runtime_trend_store_path is None or _runtime_trend_persist_seconds <= 0:
        return
    try:
        with _runtime_trend_store_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(sample, ensure_ascii=False))
            f.write("\n")
    except Exception:
        return
    _prune_runtime_trend_store_if_needed()


def _prune_runtime_trend_store_if_needed() -> None:
    global _last_prune_ts
    if _runtime_trend_store_path is None or _runtime_trend_persist_seconds <= 0:
        return
    now = time.time()
    if (now - _last_prune_ts) < 90:
        return
    cutoff = now - _runtime_trend_persist_seconds
    kept = [row for row in _runtime_trend if (_safe_float(row.get("ts")) or 0.0) >= cutoff]
    _write_runtime_trend_store(kept)
    _last_prune_ts = now


def _write_runtime_trend_store(rows: list[dict[str, float | None]]) -> None:
    if _runtime_trend_store_path is None:
        return
    try:
        with _runtime_trend_store_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False))
                f.write("\n")
    except Exception:
        return
