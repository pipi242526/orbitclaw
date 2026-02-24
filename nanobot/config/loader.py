"""Configuration loading utilities."""

import json
from copy import deepcopy
from pathlib import Path

from nanobot.config.schema import Config


def get_config_path() -> Path:
    """Get the default configuration file path."""
    return Path.home() / ".nanobot" / "config.json"


def get_data_dir() -> Path:
    """Get the nanobot data directory."""
    from nanobot.utils.helpers import get_data_path
    return get_data_path()


def load_config(config_path: Path | None = None, apply_profiles: bool = True) -> Config:
    """
    Load configuration from file or create default.

    Args:
        config_path: Optional path to config file. Uses default if not provided.
        apply_profiles: Whether to apply profiles.active overlays before validation.

    Returns:
        Loaded configuration object.
    """
    path = config_path or get_config_path()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data = _migrate_config(data)
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
