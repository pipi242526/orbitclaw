"""Provider factory helpers for RouterProvider endpoint delegates."""

from __future__ import annotations

from orbitclaw.platform.config.schema import EndpointProviderConfig
from orbitclaw.platform.providers.base import LLMProvider
from orbitclaw.platform.providers.custom_provider import CustomProvider
from orbitclaw.platform.providers.litellm_provider import LiteLLMProvider
from orbitclaw.platform.providers.resolver import LITELLM_ENDPOINT_TYPES, normalize_endpoint_type


def build_endpoint_provider(cfg: EndpointProviderConfig, endpoint_model: str) -> LLMProvider:
    endpoint_type = normalize_endpoint_type(cfg.type)
    if endpoint_type == "openai_compatible":
        return CustomProvider(
            api_key=cfg.api_key or "no-key",
            api_base=cfg.api_base or "http://localhost:8000/v1",
            default_model=endpoint_model,
        )
    if endpoint_type in LITELLM_ENDPOINT_TYPES:
        return LiteLLMProvider(
            api_key=cfg.api_key or None,
            api_base=cfg.api_base,
            default_model=endpoint_model,
            extra_headers=cfg.extra_headers or None,
            provider_name=endpoint_type,
        )
    raise ValueError(f"Unsupported endpoint type: {cfg.type}")

