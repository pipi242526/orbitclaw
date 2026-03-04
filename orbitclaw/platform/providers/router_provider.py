"""Endpoint-aware provider router with cached delegate instances."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from orbitclaw.platform.config.schema import EndpointProviderConfig
from orbitclaw.platform.providers.base import LLMProvider, LLMResponse
from orbitclaw.platform.providers.factory import build_endpoint_provider
from orbitclaw.platform.providers.health import build_error_response, list_switchable_endpoints
from orbitclaw.platform.providers.resolver import split_endpoint_model, validate_endpoint_model


class RouterProvider(LLMProvider):
    """Routes `endpoint/model` requests to endpoint-specific cached providers."""

    def __init__(
        self,
        *,
        default_model: str,
        endpoints: Mapping[str, EndpointProviderConfig] | None,
        fallback_factory: Callable[[str], LLMProvider],
    ):
        super().__init__(api_key=None, api_base=None)
        self.default_model = default_model
        self._fallback_factory = fallback_factory
        self._fallback_cache: dict[str, LLMProvider] = {}
        self._endpoints: dict[str, EndpointProviderConfig] = {
            str(name).strip(): cfg
            for name, cfg in (endpoints or {}).items()
            if str(name).strip()
        }
        self._endpoint_cache: dict[str, LLMProvider] = {}

    def _get_or_create_endpoint_provider(self, endpoint_name: str, cfg: EndpointProviderConfig, endpoint_model: str) -> LLMProvider:
        provider = self._endpoint_cache.get(endpoint_name)
        if provider is None:
            provider = build_endpoint_provider(cfg, endpoint_model)
            self._endpoint_cache[endpoint_name] = provider
        return provider

    def _get_fallback_provider(self, model: str) -> LLMProvider:
        key = model.strip()
        provider = self._fallback_cache.get(key)
        if provider is None:
            provider = self._fallback_factory(key)
            self._fallback_cache[key] = provider
        return provider

    def prepare_model(self, model: str) -> tuple[bool, str | None]:
        parsed = split_endpoint_model(model, self._endpoints)
        if not parsed:
            # Non-endpoint model path: defer to fallback provider if available.
            try:
                provider = self._get_fallback_provider(model)
            except Exception as e:
                return False, str(e)
            return provider.prepare_model(model)

        endpoint_name, cfg, endpoint_model = parsed
        ok, detail = validate_endpoint_model(endpoint_name, cfg, endpoint_model)
        if not ok:
            return False, detail
        try:
            self._get_or_create_endpoint_provider(endpoint_name, cfg, endpoint_model)
        except Exception as e:
            return False, str(e)
        return True, detail

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        active_model = model or self.default_model
        parsed = split_endpoint_model(active_model, self._endpoints)
        if not parsed:
            return await self._get_fallback_provider(active_model).chat(
                messages=messages,
                tools=tools,
                model=active_model,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        endpoint_name, cfg, endpoint_model = parsed
        ok, detail = validate_endpoint_model(endpoint_name, cfg, endpoint_model)
        if not ok:
            return build_error_response(str(detail))
        try:
            provider = self._get_or_create_endpoint_provider(endpoint_name, cfg, endpoint_model)
        except Exception as e:
            return build_error_response(str(e))
        return await provider.chat(
            messages=messages,
            tools=tools,
            model=endpoint_model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def get_default_model(self) -> str:
        return self.default_model

    def list_switchable_endpoints(self) -> dict[str, list[str]]:
        return list_switchable_endpoints(self._endpoints)
