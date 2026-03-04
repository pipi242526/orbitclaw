"""Health/error helpers for RouterProvider."""

from __future__ import annotations

from collections.abc import Mapping

from orbitclaw.platform.config.schema import EndpointProviderConfig
from orbitclaw.platform.providers.base import LLMResponse


def build_error_response(reason: str) -> LLMResponse:
    return LLMResponse(content=f"Error calling LLM: {reason}", finish_reason="error")


def list_switchable_endpoints(
    endpoints: Mapping[str, EndpointProviderConfig],
) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for name, cfg in endpoints.items():
        if not bool(getattr(cfg, "enabled", True)):
            continue
        out[name] = [str(m) for m in (cfg.models or []) if str(m).strip()]
    return out

