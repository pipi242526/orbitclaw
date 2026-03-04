"""Shared retry/backoff helpers for channel adapters."""

from __future__ import annotations

from typing import Any


def seconds_from_ms(value: int | float, *, minimum: float = 0.0) -> float:
    """Convert milliseconds to seconds with lower-bound clamp."""
    try:
        seconds = float(value) / 1000.0
    except Exception:
        seconds = 0.0
    return max(minimum, seconds)


def clamp_retry_after(
    value: Any,
    *,
    default: float = 1.0,
    minimum: float = 0.05,
    maximum: float = 120.0,
) -> float:
    """Parse a retry-after like value and clamp to safe bounds."""
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def linear_retry_delay(
    base_seconds: float,
    attempt: int,
    *,
    step_seconds: float = 1.0,
    maximum: float = 30.0,
) -> float:
    """Compute linear backoff delay for attempt index (0-based)."""
    delay = float(base_seconds) + max(0, int(attempt)) * float(step_seconds)
    return max(0.0, min(float(maximum), delay))
