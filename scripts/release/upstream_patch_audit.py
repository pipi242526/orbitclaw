#!/usr/bin/env python3
"""Generate a monthly upstream patch audit skeleton from git history."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()


def _collect_commits(upstream: str, target: str, limit: int) -> list[tuple[str, str]]:
    out = _run(["git", "log", "--oneline", f"{target}..{upstream}", f"-n{limit}"])
    commits: list[tuple[str, str]] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        sha, _, title = line.partition(" ")
        commits.append((sha, title.strip()))
    return commits


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate upstream audit markdown")
    parser.add_argument("--upstream", default="origin/main")
    parser.add_argument("--target", default="codex/dev")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--limit", type=int, default=120)
    args = parser.parse_args()

    commits = _collect_commits(args.upstream, args.target, args.limit)

    out_path = Path("release/internal/upstream-audits") / f"{args.month}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        f"# Upstream Patch Audit - {args.month}",
        "",
        f"- Upstream ref: `{args.upstream}`",
        f"- Fork ref: `{args.target}`",
        "- Auditor: `TBD`",
        "- Date: `TBD`",
        "",
        "## Summary",
        "",
        f"- Total candidates reviewed: `{len(commits)}`",
        "- Accepted: `0`",
        "- Rejected: `0`",
        "- Deferred: `0`",
        "",
        "## Decisions",
        "",
        "| Commit | Title | Status | Reason | Risk | Follow-up |",
        "|---|---|---|---|---|---|",
    ]
    for sha, title in commits:
        lines.append(
            f"| `{sha}` | {title.replace('|', '/')} | DEFER | TBD | TBD | TBD |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Focus on security/stability/correctness/context integrity patches first.",
            "- Mark non-applicable patches with explicit rationale.",
        ]
    )

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
