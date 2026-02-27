"""Runtime and context-budget diagnostics helpers."""

from __future__ import annotations

import os
import shutil
from typing import Any


def estimate_tokens_from_chars(chars: int) -> int:
    """Coarse estimate for mixed CJK+Latin prompts."""
    return max(0, int(chars / 3))


def read_host_resource_snapshot() -> dict[str, float | int | None]:
    """Collect lightweight host runtime metrics without extra dependencies."""
    out: dict[str, float | int | None] = {
        "load1": None,
        "load5": None,
        "load15": None,
        "mem_used_percent": None,
        "disk_used_percent": None,
        "cpu_cores": None,
    }
    try:
        out["cpu_cores"] = int(os.cpu_count() or 0) or None
    except Exception:
        pass

    try:
        load1, load5, load15 = os.getloadavg()
        out["load1"] = float(load1)
        out["load5"] = float(load5)
        out["load15"] = float(load15)
    except Exception:
        pass

    try:
        total = available = None
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) * 1024
                elif line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) * 1024
        if total and available is not None and total > 0:
            used = max(0, total - available)
            out["mem_used_percent"] = (used / total) * 100.0
    except Exception:
        pass

    try:
        disk = shutil.disk_usage("/")
        if disk.total > 0:
            out["disk_used_percent"] = (disk.used / disk.total) * 100.0
    except Exception:
        pass
    return out


def collect_runtime_budget_alerts(config: Any, snapshot: dict[str, float | int | None]) -> list[dict[str, str]]:
    """Return budget/host alerts with severity and actionable suggestions."""
    alerts: list[dict[str, str]] = []
    defaults = config.agents.defaults

    history_chars = int(defaults.max_history_chars or 0)
    memory_chars = int(defaults.max_memory_context_chars or 0)
    background_chars = int(defaults.max_background_context_chars or 0)
    inline_image_bytes = int(defaults.max_inline_image_bytes or 0)
    total_chars = max(0, history_chars + memory_chars + background_chars)
    total_tokens = estimate_tokens_from_chars(total_chars)

    # Keep defaults green; only alert when budgets exceed normal baseline significantly.
    if total_tokens >= 36000:
        alerts.append(
            {
                "severity": "error",
                "message": f"context token budget too high (~{total_tokens})",
                "suggestion": "reduce history/memory/background char caps in Models & APIs > 资源与上下文预算",
            }
        )
    elif total_tokens >= 28000:
        alerts.append(
            {
                "severity": "warn",
                "message": f"context token budget is high (~{total_tokens})",
                "suggestion": "consider lowering background/history budgets for lower cost",
            }
        )

    if inline_image_bytes >= 1_500_000:
        alerts.append(
            {
                "severity": "warn",
                "message": f"inline image cap is high ({inline_image_bytes} bytes)",
                "suggestion": "prefer <= 400000 to avoid large token spikes on image turns",
            }
        )

    if int(defaults.gc_every_turns or 0) == 0:
        alerts.append(
            {
                "severity": "warn",
                "message": "gcEveryTurns is 0 (periodic GC disabled)",
                "suggestion": "set gcEveryTurns to 8-20 for long-running gateways",
            }
        )

    if int(defaults.session_cache_max_entries or 0) > 64:
        alerts.append(
            {
                "severity": "warn",
                "message": f"session cache is large ({defaults.session_cache_max_entries})",
                "suggestion": "use <= 32 unless high concurrency is required",
            }
        )

    mem_used = snapshot.get("mem_used_percent")
    if isinstance(mem_used, float):
        if mem_used >= 92:
            alerts.append(
                {
                    "severity": "error",
                    "message": f"host memory usage is very high ({mem_used:.1f}%)",
                    "suggestion": "reduce budgets, disable heavy skills/tools, or scale host memory",
                }
            )
        elif mem_used >= 82:
            alerts.append(
                {
                    "severity": "warn",
                    "message": f"host memory usage is high ({mem_used:.1f}%)",
                    "suggestion": "monitor long chats; lower context budgets if pressure persists",
                }
            )

    disk_used = snapshot.get("disk_used_percent")
    if isinstance(disk_used, float) and disk_used >= 90:
        alerts.append(
            {
                "severity": "warn",
                "message": f"disk usage is high ({disk_used:.1f}%)",
                "suggestion": "clean media/exports and old Docker artifacts",
            }
        )

    load1 = snapshot.get("load1")
    cpu_cores = snapshot.get("cpu_cores")
    if isinstance(load1, float) and isinstance(cpu_cores, int) and cpu_cores > 0:
        if load1 >= cpu_cores * 1.8:
            alerts.append(
                {
                    "severity": "warn",
                    "message": f"host CPU load is high (load1={load1:.2f}, cores={cpu_cores})",
                    "suggestion": "reduce concurrent channel traffic or scale CPU",
                }
            )

    return alerts
