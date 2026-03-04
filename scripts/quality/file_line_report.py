#!/usr/bin/env python3
"""Non-blocking file line-count report for architecture hygiene."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

DEFAULT_SCAN_ROOTS = ("lunaeclaw",)
DEFAULT_EXCLUDES = {
    "lunaeclaw/app/webui/copy_catalog.py",  # generated catalog, intentionally large
}


@dataclass(frozen=True)
class FileStat:
    path: Path
    lines: int


def iter_python_files(roots: Iterable[Path], excludes: set[str]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            rel = str(path.as_posix())
            if rel in excludes:
                continue
            files.append(path)
    return sorted(files)


def count_lines(path: Path) -> int:
    # splitlines() keeps behavior stable across LF/CRLF files.
    return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())


def report(stats: list[FileStat], warn_threshold: int, critical_threshold: int, top_n: int) -> None:
    total = len(stats)
    warn = [s for s in stats if s.lines >= warn_threshold]
    critical = [s for s in stats if s.lines >= critical_threshold]

    print("=== file-line-report (non-blocking) ===")
    print(f"Scanned Python files: {total}")
    print(f"Warn threshold: {warn_threshold}")
    print(f"Critical threshold: {critical_threshold}")
    print()

    largest = sorted(stats, key=lambda s: s.lines, reverse=True)[:top_n]
    print(f"Top {min(top_n, len(largest))} largest files:")
    for item in largest:
        print(f"- {item.lines:4d}  {item.path.as_posix()}")
    print()

    if not warn:
        print(f"No files at or above warn threshold ({warn_threshold}).")
        print("Report complete.")
        return

    print(f"Files at or above {warn_threshold} lines: {len(warn)}")
    for item in sorted(warn, key=lambda s: s.lines, reverse=True):
        level = "CRITICAL" if item.lines >= critical_threshold else "WARN"
        print(f"- [{level}] {item.lines:4d}  {item.path.as_posix()}")
    print()

    print(f"Critical files at or above {critical_threshold} lines: {len(critical)}")
    print("Report complete. (No CI blocking)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Non-blocking file line-count report.")
    parser.add_argument(
        "--roots",
        nargs="+",
        default=list(DEFAULT_SCAN_ROOTS),
        help="Directories to scan for Python files.",
    )
    parser.add_argument(
        "--warn-threshold",
        type=int,
        default=600,
        help="Warn threshold in lines (report only).",
    )
    parser.add_argument(
        "--critical-threshold",
        type=int,
        default=800,
        help="Critical threshold in lines (report only).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=15,
        help="Number of largest files to print.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = [Path(p) for p in args.roots]
    files = iter_python_files(roots, excludes=DEFAULT_EXCLUDES)
    stats = [FileStat(path=f, lines=count_lines(f)) for f in files]
    report(
        stats,
        warn_threshold=max(0, args.warn_threshold),
        critical_threshold=max(0, args.critical_threshold),
        top_n=max(1, args.top),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
