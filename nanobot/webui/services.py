"""Reusable WebUI service helpers."""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path


def safe_positive_int(raw: str | None, *, default: int = 1, minimum: int = 1) -> int:
    try:
        value = int((raw or "").strip())
    except Exception:
        return default
    return value if value >= minimum else default


def short_text(raw: str, *, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", (raw or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _detect_compose_dirs() -> list[Path]:
    candidates: list[Path] = []
    from_env = (os.getenv("NANOBOT_WEBUI_COMPOSE_DIR") or "").strip()
    if from_env:
        candidates.append(Path(from_env).expanduser())
    candidates.extend([Path.cwd(), Path("/root/nanobot-s"), Path("/app")])
    out: list[Path] = []
    compose_files = ("docker-compose.yml", "compose.yml", "compose.yaml")
    for path in candidates:
        p = path.resolve()
        if p in out:
            continue
        if any((p / name).exists() for name in compose_files):
            out.append(p)
    return out


def _run_cmd(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 30,
) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return False, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return False, f"timeout after {timeout}s: {' '.join(cmd)}"
    output = "\n".join(x for x in [proc.stdout.strip(), proc.stderr.strip()] if x).strip()
    if proc.returncode == 0:
        return True, output or "ok"
    return False, output or f"exit code {proc.returncode}"


def restart_gateway_runtime() -> tuple[bool, str]:
    override = (os.getenv("NANOBOT_WEBUI_RESTART_GATEWAY_CMD") or "").strip()
    if override:
        cmd = shlex.split(override)
        if not cmd:
            return False, "NANOBOT_WEBUI_RESTART_GATEWAY_CMD is empty after parsing"
        ok, output = _run_cmd(cmd, timeout=45)
        if ok:
            return True, f"restart command ok: {' '.join(cmd)}"
        return False, f"restart command failed: {output}"

    candidates: list[tuple[list[str], Path | None]] = []
    compose_dirs = _detect_compose_dirs()
    if shutil.which("docker"):
        for compose_dir in compose_dirs:
            candidates.append((["docker", "compose", "restart", "nanobot-gateway"], compose_dir))
        container_name = (os.getenv("NANOBOT_GATEWAY_CONTAINER") or "").strip() or "nanobot-gateway"
        for name in {container_name, "nanobot-gateway"}:
            candidates.append((["docker", "restart", name], None))
    if shutil.which("docker-compose"):
        for compose_dir in compose_dirs:
            candidates.append((["docker-compose", "restart", "nanobot-gateway"], compose_dir))

    if not candidates:
        return False, (
            "No restart backend detected. Set NANOBOT_WEBUI_RESTART_GATEWAY_CMD "
            "or install docker/docker-compose CLI."
        )

    errors: list[str] = []
    for cmd, cwd in candidates:
        ok, output = _run_cmd(cmd, cwd=cwd, timeout=45)
        if ok:
            suffix = f" (cwd={cwd})" if cwd else ""
            return True, f"{' '.join(cmd)}{suffix}"
        errors.append(f"{' '.join(cmd)} => {short_text(output)}")
    return False, " ; ".join(errors[:3])

