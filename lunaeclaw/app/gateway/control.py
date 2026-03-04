"""Gateway runtime control helpers."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path


def discover_runtime_env_files() -> list[Path]:
    """Return env helper files that affect config interpolation."""
    explicit = os.environ.get("ORBITCLAW_ENV_FILES", "").strip()
    files: list[Path] = []
    if explicit:
        for raw in explicit.split(os.pathsep):
            p = Path(raw).expanduser()
            if p.exists() and p.is_file():
                files.append(p)
        return files

    from orbitclaw.platform.utils.helpers import get_env_dir, get_env_file

    primary = get_env_file()
    if primary.exists() and primary.is_file():
        files.append(primary)
    env_dir = get_env_dir()
    if env_dir.exists() and env_dir.is_dir():
        files.extend(sorted(p for p in env_dir.glob("*.env") if p.is_file()))
    return files


def compute_runtime_config_fingerprint(config_path: Path) -> str:
    """
    Build a stable fingerprint from config.json and env helper files.

    The gateway uses this to detect runtime-affecting changes and trigger a
    safe in-process reload.
    """
    hasher = hashlib.sha256()
    seen: set[Path] = set()
    files = [config_path, *discover_runtime_env_files()]
    for raw_path in files:
        path = raw_path.expanduser().resolve()
        if path in seen:
            continue
        seen.add(path)
        hasher.update(str(path).encode("utf-8"))
        hasher.update(b"\0")
        if not path.exists() or not path.is_file():
            hasher.update(b"MISSING")
            hasher.update(b"\0")
            continue
        try:
            hasher.update(hashlib.sha256(path.read_bytes()).digest())
        except OSError as e:
            hasher.update(f"READ_ERROR:{e}".encode("utf-8", errors="replace"))
        hasher.update(b"\0")
    return hasher.hexdigest()


def get_gateway_runtime_state_path(config_path: Path) -> Path:
    """Return runtime state file path colocated with config."""
    root = config_path.expanduser().resolve().parent / "runtime"
    root.mkdir(parents=True, exist_ok=True)
    return root / "gateway.state.json"


def write_gateway_runtime_state(
    config_path: Path,
    *,
    fingerprint: str,
    status: str,
    note: str = "",
) -> Path:
    """Persist gateway runtime state atomically for cross-process coordination."""
    state_path = get_gateway_runtime_state_path(config_path)
    payload = {
        "status": status,
        "fingerprint": str(fingerprint or ""),
        "note": str(note or ""),
        "pid": os.getpid(),
        "configPath": str(config_path.expanduser().resolve()),
        "dataDir": str(config_path.expanduser().resolve().parent),
        "updatedAt": time.time(),
    }
    tmp_path = state_path.with_name(f".{state_path.name}.tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_path, state_path)
    return state_path


def read_gateway_runtime_state(config_path: Path) -> dict | None:
    """Read gateway runtime state. Returns None when unavailable/invalid."""
    state_path = get_gateway_runtime_state_path(config_path)
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


def is_gateway_runtime_fresh(state: dict | None, *, max_age_seconds: float = 12.0) -> bool:
    """Return True when runtime state indicates a recently alive gateway."""
    if not isinstance(state, dict):
        return False
    if str(state.get("status") or "").lower() != "running":
        return False
    try:
        updated_at = float(state.get("updatedAt"))
    except Exception:
        return False
    return (time.time() - updated_at) <= max(1.0, float(max_age_seconds))
