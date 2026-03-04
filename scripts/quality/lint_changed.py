#!/usr/bin/env python3
"""Run ruff only on changed Python files to enforce incremental cleanliness."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run_lines(cmd: list[str]) -> list[str]:
    completed = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _git_ref_exists(ref: str) -> bool:
    return (
        subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", ref],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )


def resolve_base(explicit_base: str) -> str:
    requested = explicit_base.strip()
    if requested:
        if _git_ref_exists(requested):
            return requested
        print(f"Warning: base ref not found: {requested!r}. Falling back to defaults.")

    for candidate in _default_base_candidates():
        if _git_ref_exists(candidate):
            return candidate
    return "HEAD"


def _default_base_candidates() -> list[str]:
    baseline_file = Path("release/lint-baseline.txt")
    candidates: list[str] = []
    if baseline_file.exists():
        value = baseline_file.read_text(encoding="utf-8").strip()
        if value:
            candidates.append(value)
    candidates.extend(["origin/main", "main"])
    return candidates


def changed_files(base: str) -> list[Path]:
    file_set: set[Path] = set()
    committed = _run_lines(["git", "diff", "--name-only", f"{base}...HEAD"])
    for line in committed:
        p = Path(line.strip())
        if p.suffix == ".py" and p.exists():
            file_set.add(p)

    # Include local unstaged + staged changes for developer runs.
    local_diffs = (
        ["git", "diff", "--name-only"],
        ["git", "diff", "--name-only", "--cached"],
    )
    for cmd in local_diffs:
        for line in _run_lines(cmd):
            p = Path(line.strip())
            if p.suffix == ".py" and p.exists():
                file_set.add(p)

    # Include newly added untracked Python files.
    untracked = _run_lines(["git", "ls-files", "--others", "--exclude-standard"])
    for line in untracked:
        p = Path(line.strip())
        if p.suffix == ".py" and p.exists():
            file_set.add(p)
    return sorted(file_set)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="", help="git base ref for incremental lint")
    args = parser.parse_args()

    base = resolve_base(args.base)
    files = changed_files(base)
    if not files:
        print("No changed Python files. Incremental lint passed.")
        return 0

    cmd = ["uv", "run", "ruff", "check", *[str(p) for p in files]]
    print(f"Base ref: {base}")
    print("Running:", " ".join(cmd))
    completed = subprocess.run(cmd)
    if completed.returncode != 0:
        print("\nIncremental lint failed.")
        return completed.returncode

    print("Incremental lint passed for changed files:")
    for p in files:
        print(f"- {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
