"""Shared endpoint/default-model validation helpers for WebUI + CLI."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from lunaeclaw.platform.config.schema import Config
from lunaeclaw.platform.providers.resolver import LITELLM_ENDPOINT_TYPES, normalize_endpoint_type

SUPPORTED_ENDPOINT_TYPES: set[str] = {"openai_compatible", *LITELLM_ENDPOINT_TYPES}


@dataclass(frozen=True)
class EndpointDiagnosticFinding:
    severity: str
    problem: str
    fix: str


def parse_endpoint_model_ref(model_ref: str) -> tuple[str, str] | None:
    text = (model_ref or "").strip()
    if "/" not in text:
        return None
    endpoint_name, model_name = text.split("/", 1)
    endpoint_name = endpoint_name.strip()
    model_name = model_name.strip()
    if not endpoint_name or not model_name:
        return None
    return endpoint_name, model_name


def _build_models_url(api_base: str) -> str:
    base = (api_base or "").strip().rstrip("/")
    if base.endswith("/models"):
        return base
    return f"{base}/models"


def validate_default_model_reference(
    config: Config,
    model_ref: str,
    *,
    probe_remote: bool = False,
) -> tuple[bool, str]:
    parsed = parse_endpoint_model_ref(model_ref)
    if not parsed:
        return False, "default model must be in endpoint/model format"

    endpoint_name, model_name = parsed
    endpoint_cfg = config.providers.endpoints.get(endpoint_name)
    if endpoint_cfg is None:
        return False, f"endpoint not found: {endpoint_name}"
    if not endpoint_cfg.enabled:
        return False, f"endpoint is disabled: {endpoint_name}"

    endpoint_type = normalize_endpoint_type(endpoint_cfg.type)
    if endpoint_type not in SUPPORTED_ENDPOINT_TYPES:
        return False, f"endpoint '{endpoint_name}' uses unsupported type '{endpoint_cfg.type}'"

    if endpoint_cfg.models:
        allowed = {str(x).strip() for x in endpoint_cfg.models if str(x).strip()}
        full_ref = f"{endpoint_name}/{model_name}"
        if model_name not in allowed and full_ref not in allowed:
            return False, f"model '{model_name}' is not listed in endpoint '{endpoint_name}'"

    if endpoint_type not in {"openai", "openai_compatible"}:
        return True, "ok (structural check)"
    if not probe_remote:
        return True, "ok (structural check)"
    if not endpoint_cfg.api_base:
        return False, f"endpoint '{endpoint_name}' has empty api_base"

    headers: dict[str, str] = {"Accept": "application/json", "User-Agent": "lunaeclaw-webui/0.1"}
    if endpoint_cfg.api_key:
        headers["Authorization"] = f"Bearer {endpoint_cfg.api_key}"
    if endpoint_cfg.extra_headers:
        headers.update({str(k): str(v) for k, v in endpoint_cfg.extra_headers.items()})

    url = _build_models_url(endpoint_cfg.api_base)
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return False, f"probe failed for endpoint '{endpoint_name}': {e}"

    data = payload.get("data")
    if isinstance(data, list):
        ids = {str(item.get("id", "")).strip() for item in data if isinstance(item, dict)}
        ids.discard("")
        if ids and model_name not in ids:
            return False, f"model '{model_name}' not returned by {endpoint_name}/models"
    return True, "ok"


def collect_default_model_endpoint_findings(config: Config) -> list[EndpointDiagnosticFinding]:
    active_model = str(config.agents.defaults.model or "")
    parsed = parse_endpoint_model_ref(active_model)
    if not parsed:
        return []

    endpoint_name, endpoint_model = parsed
    endpoint_cfg = config.providers.endpoints.get(endpoint_name)
    if endpoint_cfg is None:
        return []

    findings: list[EndpointDiagnosticFinding] = []
    endpoint_type = normalize_endpoint_type(endpoint_cfg.type)

    if not endpoint_cfg.enabled:
        findings.append(
            EndpointDiagnosticFinding(
                severity="error",
                problem=f"endpoint is disabled: {endpoint_name}",
                fix=f"Enable providers.endpoints.{endpoint_name}.enabled or switch agents.defaults.model to another endpoint/model.",
            )
        )

    if endpoint_type not in SUPPORTED_ENDPOINT_TYPES:
        findings.append(
            EndpointDiagnosticFinding(
                severity="error",
                problem=f"endpoint '{endpoint_name}' uses unsupported type '{endpoint_cfg.type}'",
                fix="Use openai_compatible or a supported provider type (anthropic/openrouter/openai/... ).",
            )
        )

    allowed = {str(x).strip() for x in (endpoint_cfg.models or []) if str(x).strip()}
    if allowed:
        full_ref = f"{endpoint_name}/{endpoint_model}"
        if endpoint_model not in allowed and full_ref not in allowed:
            findings.append(
                EndpointDiagnosticFinding(
                    severity="warn",
                    problem=f"model '{endpoint_model}' is not listed in endpoint '{endpoint_name}'",
                    fix=f"Add the model to providers.endpoints.{endpoint_name}.models or clear the list to allow any model.",
                )
            )

    if endpoint_type == "openai_compatible" and not endpoint_cfg.api_base:
        findings.append(
            EndpointDiagnosticFinding(
                severity="warn",
                problem=f"endpoint '{endpoint_name}' has empty api_base",
                fix=f"Set providers.endpoints.{endpoint_name}.apiBase to your OpenAI-compatible endpoint.",
            )
        )

    if endpoint_cfg.api_key and "${" in str(endpoint_cfg.api_key):
        findings.append(
            EndpointDiagnosticFinding(
                severity="warn",
                problem=f"providers.endpoints.{endpoint_name}.apiKey contains an unresolved ${'{'}ENV_VAR{'}'} placeholder",
                fix="Check ~/.lunaeclaw/.env or ~/.lunaeclaw/env/*.env and ensure the referenced variable exists.",
            )
        )

    return findings

