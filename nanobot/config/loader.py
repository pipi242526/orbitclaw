"""Configuration loading utilities."""

import json
import os
import re
from copy import deepcopy
from pathlib import Path

from nanobot.config.schema import Config


def get_config_path() -> Path:
    """Get the default configuration file path."""
    from nanobot.utils.helpers import get_config_file
    return get_config_file()


def get_data_dir() -> Path:
    """Get the nanobot data directory."""
    from nanobot.utils.helpers import get_data_path
    return get_data_path()


def load_config(
    config_path: Path | None = None,
    apply_profiles: bool = True,
    resolve_env: bool = True,
) -> Config:
    """
    Load configuration from file or create default.

    Args:
        config_path: Optional path to config file. Uses default if not provided.
        apply_profiles: Whether to apply profiles.active overlays before validation.
        resolve_env: Whether to expand ${ENV_VAR} placeholders in JSON string values.

    Returns:
        Loaded configuration object.
    """
    path = config_path or get_config_path()
    _load_env_files()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data = _migrate_config(data)
            if resolve_env:
                data = _interpolate_env_placeholders(data)
            if apply_profiles:
                data = _apply_active_profile(data)
            return Config.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration.")

    return Config()


def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration to save.
        config_path: Optional path to save to. Uses default if not provided.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(by_alias=True)
    data = _slim_config_for_save(data)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _migrate_config(data: dict) -> dict:
    """Migrate old config formats to current."""
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data


def inspect_config_hints(config_path: Path | None = None) -> list[str]:
    """
    Inspect raw config file and return lightweight migration/validation hints.

    This is non-blocking diagnostics used by Web UI / doctor-like screens.
    """
    path = config_path or get_config_path()
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [f"config parse error: {e}"]
    except Exception as e:
        return [f"config read error: {e}"]
    return _collect_raw_config_hints(data)


def _collect_raw_config_hints(data: dict) -> list[str]:
    hints: list[str] = []
    if not isinstance(data, dict):
        return ["config root should be a JSON object"]

    tools = data.get("tools") or {}
    if isinstance(tools, dict):
        exec_cfg = tools.get("exec") or {}
        if (
            isinstance(exec_cfg, dict)
            and "restrictToWorkspace" in exec_cfg
            and "restrictToWorkspace" not in tools
        ):
            hints.append(
                "legacy key `tools.exec.restrictToWorkspace` detected; it will be migrated to `tools.restrictToWorkspace`"
            )

        web_cfg = tools.get("web") or {}
        if isinstance(web_cfg, dict):
            search_cfg = web_cfg.get("search") or {}
            if isinstance(search_cfg, dict):
                provider = str(search_cfg.get("provider") or "").strip().lower()
                if provider in {"auto", "brave"}:
                    hints.append("legacy web.search.provider detected (`auto/brave`); use `exa_mcp` or `disabled`")
                elif provider and provider not in {"exa_mcp", "disabled"}:
                    hints.append(f"unknown web.search.provider `{provider}`; expected `exa_mcp` or `disabled`")

        for key in ("enabled", "mcpEnabledServers", "mcpDisabledServers", "mcpEnabledTools", "mcpDisabledTools"):
            raw = tools.get(key)
            if not isinstance(raw, list):
                continue
            seen: set[str] = set()
            dup: list[str] = []
            for item in raw:
                text = str(item).strip()
                if not text:
                    continue
                if text in seen and text not in dup:
                    dup.append(text)
                seen.add(text)
            if dup:
                hints.append(f"`tools.{key}` contains duplicates: {', '.join(dup)}")

        aliases = tools.get("aliases")
        if isinstance(aliases, dict):
            for raw_key, raw_val in aliases.items():
                k = str(raw_key).strip()
                v = str(raw_val).strip()
                if not k or not v:
                    hints.append("`tools.aliases` contains blank key/value")
                    break
                if k == v:
                    hints.append(f"`tools.aliases` contains self mapping: {k} -> {v}")

    providers = data.get("providers") or {}
    if isinstance(providers, dict):
        endpoints = providers.get("endpoints") or {}
        if isinstance(endpoints, dict):
            for ep_name, ep_cfg in endpoints.items():
                if not isinstance(ep_cfg, dict):
                    continue
                models = ep_cfg.get("models")
                if isinstance(models, list):
                    for item in models:
                        text = str(item).strip()
                        if text.startswith(f"{ep_name}/"):
                            hints.append(
                                f"endpoint `{ep_name}` model allowlist uses endpoint prefix (`{text}`); store plain model names"
                            )
                            break

    channels = data.get("channels") or {}
    if isinstance(channels, dict):
        if channels.get("sendToolHints") is True:
            hints.append("`channels.sendToolHints=true` may leak tool invocation traces; recommend false")

    return hints


def _dedupe_strings(items: list) -> list:
    seen: set[str] = set()
    out: list = []
    for item in items or []:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _slim_config_for_save(data: dict) -> dict:
    """Prune duplicate/invalid config entries without changing intended behavior."""
    if not isinstance(data, dict):
        return data

    tools = data.get("tools")
    if isinstance(tools, dict):
        for key in ("enabled", "mcpEnabledServers", "mcpDisabledServers", "mcpEnabledTools", "mcpDisabledTools"):
            if isinstance(tools.get(key), list):
                tools[key] = _dedupe_strings(tools[key])

        aliases = tools.get("aliases")
        if isinstance(aliases, dict):
            cleaned_aliases: dict[str, str] = {}
            for raw_key, raw_value in aliases.items():
                key = str(raw_key).strip()
                value = str(raw_value).strip()
                if not key or not value or key == value:
                    continue
                cleaned_aliases[key] = value
            tools["aliases"] = cleaned_aliases

        web_cfg = tools.get("web")
        if isinstance(web_cfg, dict):
            search_cfg = web_cfg.get("search")
            if isinstance(search_cfg, dict):
                provider = str(search_cfg.get("provider") or "exa_mcp").strip().lower()
                if provider not in {"exa_mcp", "disabled"}:
                    search_cfg["provider"] = "exa_mcp"
                else:
                    search_cfg["provider"] = provider
                search_cfg.pop("apiKey", None)

    skills = data.get("skills")
    if isinstance(skills, dict) and isinstance(skills.get("disabled"), list):
        skills["disabled"] = _dedupe_strings(skills["disabled"])

    providers = data.get("providers")
    if isinstance(providers, dict):
        endpoints = providers.get("endpoints")
        if isinstance(endpoints, dict):
            cleaned_endpoints: dict[str, dict] = {}
            for raw_name, raw_cfg in endpoints.items():
                name = str(raw_name).strip()
                if not name or not isinstance(raw_cfg, dict):
                    continue
                cfg = dict(raw_cfg)
                cfg_type = str(cfg.get("type") or "openai_compatible").strip().lower()
                cfg["type"] = cfg_type.replace("-", "_")
                if isinstance(cfg.get("models"), list):
                    cfg["models"] = _dedupe_strings(cfg["models"])
                cleaned_endpoints[name] = cfg
            providers["endpoints"] = cleaned_endpoints

    return data


_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-(.*?))?\}")


def _discover_env_files() -> list[Path]:
    """Find optional env files for secrets/API keys."""
    files: list[Path] = []
    explicit = os.environ.get("NANOBOT_ENV_FILES", "").strip()
    if explicit:
        for raw in explicit.split(os.pathsep):
            p = Path(raw).expanduser()
            if p.exists() and p.is_file():
                files.append(p)
        return files

    from nanobot.utils.helpers import get_env_file, get_env_dir
    primary = get_env_file()
    if primary.exists() and primary.is_file():
        files.append(primary)
    env_dir = get_env_dir()
    if env_dir.exists() and env_dir.is_dir():
        files.extend(sorted(p for p in env_dir.glob("*.env") if p.is_file()))
    return files


def _parse_env_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        return None
    key, val = line.split("=", 1)
    key = key.strip()
    if not key:
        return None
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    return key, val


def _load_env_files() -> None:
    """Load env vars from ~/.nanobot/.env and ~/.nanobot/env/*.env without overriding existing vars."""
    for path in _discover_env_files():
        try:
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                parsed = _parse_env_line(raw_line)
                if not parsed:
                    continue
                key, val = parsed
                os.environ.setdefault(key, val)
        except Exception:
            # Keep config loading resilient even if a helper env file is malformed.
            continue


def _expand_env_placeholders(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        default = match.group(2)
        return os.environ.get(key, default if default is not None else match.group(0))
    return _ENV_VAR_PATTERN.sub(_replace, text)


def _interpolate_env_placeholders(data):
    """Recursively replace ${VAR} placeholders in JSON config values."""
    if isinstance(data, dict):
        return {k: _interpolate_env_placeholders(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_interpolate_env_placeholders(v) for v in data]
    if isinstance(data, str):
        return _expand_env_placeholders(data)
    return data


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge dictionaries, with `override` values winning."""
    result = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _apply_active_profile(data: dict) -> dict:
    """Apply `profiles.active` overrides as defaults (top-level config still wins)."""
    if not isinstance(data, dict):
        return data
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        return data

    active = str(profiles.get("active") or "").strip()
    if not active:
        return data

    items = profiles.get("items") or {}
    if not isinstance(items, dict):
        return data

    profile = items.get(active)
    if not isinstance(profile, dict):
        return data

    out = deepcopy(data)
    for section in ("tools", "skills"):
        pval = profile.get(section)
        if isinstance(pval, dict):
            out[section] = _deep_merge(pval, out.get(section, {}))
    return out
