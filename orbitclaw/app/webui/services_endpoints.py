"""Service helpers for WebUI endpoint mutations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orbitclaw.platform.config.loader import load_config
from orbitclaw.platform.config.schema import EndpointProviderConfig
from orbitclaw.platform.providers.endpoint_validator import validate_default_model_reference


def validate_default_model(cfg_path: Path, model: str) -> tuple[bool, str]:
    """Validate default model against current provider settings."""
    return validate_default_model_reference(
        load_config(cfg_path, apply_profiles=False, resolve_env=True),
        model,
        probe_remote=True,
    )


def apply_default_model(cfg: Any, *, model: str) -> None:
    cfg.agents.defaults.model = model


def apply_agent_preferences(
    cfg: Any,
    *,
    reply_language: str,
    fallback_language: str,
    cross_lingual_search: bool,
) -> None:
    cfg.agents.defaults.reply_language = reply_language
    cfg.agents.defaults.auto_reply_fallback_language = fallback_language
    cfg.agents.defaults.cross_lingual_search = cross_lingual_search


def apply_runtime_budget(cfg: Any, *, values: dict[str, int | bool]) -> None:
    defaults = cfg.agents.defaults
    defaults.max_history_chars = int(values["max_history_chars"])
    defaults.max_memory_context_chars = int(values["max_memory_context_chars"])
    defaults.max_background_context_chars = int(values["max_background_context_chars"])
    defaults.max_inline_image_bytes = int(values["max_inline_image_bytes"])
    defaults.auto_compact_background = bool(values["auto_compact_background"])
    defaults.system_prompt_cache_ttl_seconds = int(values["system_prompt_cache_ttl_seconds"])
    defaults.session_cache_max_entries = int(values["session_cache_max_entries"])
    defaults.gc_every_turns = int(values["gc_every_turns"])
    defaults.turn_timeout_seconds = int(values["turn_timeout_seconds"])
    defaults.inbound_queue_maxsize = int(values["inbound_queue_maxsize"])
    defaults.outbound_queue_maxsize = int(values["outbound_queue_maxsize"])


def delete_endpoint(cfg: Any, *, name: str) -> bool:
    if name not in cfg.providers.endpoints:
        return False
    del cfg.providers.endpoints[name]
    return True


def normalize_endpoint_models(name: str, models: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in models:
        text = item.strip()
        if text.startswith(f"{name}/"):
            text = text[len(name) + 1 :].strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def save_endpoint(
    cfg: Any,
    *,
    original_name: str,
    name: str,
    cfg_type: str,
    api_base: str | None,
    api_key: str,
    headers: dict[str, Any],
    models: list[str],
    enabled: bool,
) -> None:
    ep = EndpointProviderConfig(
        type=cfg_type,
        api_base=api_base,
        api_key=api_key,
        extra_headers=headers or None,
        models=models,
        enabled=enabled,
    )
    if original_name and original_name != name and original_name in cfg.providers.endpoints:
        del cfg.providers.endpoints[original_name]
    cfg.providers.endpoints[name] = ep
