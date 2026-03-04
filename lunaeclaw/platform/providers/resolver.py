"""Endpoint/model resolver helpers for RouterProvider."""

from __future__ import annotations

from collections.abc import Mapping

from lunaeclaw.platform.config.schema import EndpointProviderConfig
from lunaeclaw.platform.providers.registry import find_by_name

ENDPOINT_TYPE_ALIASES = {
    "openai-compatible": "openai_compatible",
    "openai_compat": "openai_compatible",
    "custom": "openai_compatible",
}

LITELLM_ENDPOINT_TYPES = {
    "anthropic",
    "openai",
    "openrouter",
    "deepseek",
    "groq",
    "zhipu",
    "dashscope",
    "vllm",
    "gemini",
    "moonshot",
    "minimax",
    "aihubmix",
    "siliconflow",
    "volcengine",
}


def normalize_endpoint_type(value: str | None) -> str:
    raw = (value or "openai_compatible").strip().lower()
    return ENDPOINT_TYPE_ALIASES.get(raw, raw)


def split_endpoint_model(
    model: str | None,
    endpoints: Mapping[str, EndpointProviderConfig],
) -> tuple[str, EndpointProviderConfig, str] | None:
    text = (model or "").strip()
    if "/" not in text:
        return None
    endpoint_name, endpoint_model = text.split("/", 1)
    endpoint_name = endpoint_name.strip()
    endpoint_model = endpoint_model.strip()
    if not endpoint_name or not endpoint_model:
        return None
    cfg = endpoints.get(endpoint_name)
    if not cfg or not bool(getattr(cfg, "enabled", True)):
        return None
    return endpoint_name, cfg, endpoint_model


def validate_endpoint_model(
    endpoint_name: str,
    cfg: EndpointProviderConfig,
    endpoint_model: str,
) -> tuple[bool, str | None]:
    allowed = [m for m in (cfg.models or []) if str(m).strip()]
    if allowed:
        full_ref = f"{endpoint_name}/{endpoint_model}"
        if endpoint_model not in allowed and full_ref not in allowed:
            return False, f"模型 `{endpoint_model}` 不在 endpoint `{endpoint_name}` 的允许列表中"

    endpoint_type = normalize_endpoint_type(cfg.type)
    if endpoint_type == "openai_compatible":
        return True, f"{endpoint_name} ({endpoint_type})"
    if endpoint_type in LITELLM_ENDPOINT_TYPES and find_by_name(endpoint_type):
        return True, f"{endpoint_name} ({endpoint_type})"
    return False, f"endpoint `{endpoint_name}` 使用了不支持的类型 `{cfg.type}`"

