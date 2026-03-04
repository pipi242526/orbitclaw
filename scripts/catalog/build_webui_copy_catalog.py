#!/usr/bin/env python3
"""Build WEBUI_COPY_CATALOG from static translation-pair callsites."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEBUI_DIR = ROOT / "lunaeclaw" / "app" / "webui"
OUT = WEBUI_DIR / "copy_catalog.py"


def copy_key(en: str, zh: str) -> str:
    digest = hashlib.sha1(f"{en}\n{zh}".encode("utf-8")).hexdigest()
    return f"copy_{digest[:10]}"


def extract_pairs(path: Path) -> list[tuple[str, str]]:
    code = path.read_text(encoding="utf-8")
    tree = ast.parse(code)
    pairs: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = None
        if isinstance(fn, ast.Name):
            name = fn.id
        elif isinstance(fn, ast.Attribute):
            name = fn.attr
        if name not in {"_ui_copy", "t", "t_dyn", "_tr"}:
            continue
        min_args = 3 if name == "_ui_copy" else 2
        if len(node.args) < min_args:
            continue
        if name == "_ui_copy":
            en_arg = node.args[1]
            zh_arg = node.args[2]
        else:
            en_arg = node.args[0]
            zh_arg = node.args[1]
        if isinstance(en_arg, ast.Constant) and isinstance(zh_arg, ast.Constant):
            if isinstance(en_arg.value, str) and isinstance(zh_arg.value, str):
                pairs.append((en_arg.value, zh_arg.value))
    return pairs


def main() -> int:
    pairs: dict[str, tuple[str, str]] = {}
    for path in sorted(WEBUI_DIR.glob("*.py")):
        if path.name in {"copy_catalog.py"}:
            continue
        for en, zh in extract_pairs(path):
            pairs[copy_key(en, zh)] = (en, zh)

    lines = [
        '"""Auto-generated WebUI copy catalog for i18n key lookup."""',
        "",
        "from __future__ import annotations",
        "",
        "WEBUI_COPY_CATALOG: dict[str, dict[str, str]] = {",
    ]
    for key in sorted(pairs):
        en, zh = pairs[key]
        lines.append(f'    "{key}": {{"en": {en!r}, "zh-CN": {zh!r}}},')
    lines.append("}")
    lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"updated {OUT}")
    print(f"entries: {len(pairs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
