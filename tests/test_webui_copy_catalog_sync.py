from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from orbitclaw.webui.copy_catalog import WEBUI_COPY_CATALOG

ROOT = Path(__file__).resolve().parents[1]
WEBUI_DIR = ROOT / "orbitclaw" / "webui"


def _copy_key(en: str, zh: str) -> str:
    digest = hashlib.sha1(f"{en}\n{zh}".encode("utf-8")).hexdigest()
    return f"copy_{digest[:10]}"


def _extract_expected_keys(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
        if name not in {"t", "t_dyn", "_tr", "_ui_copy"}:
            continue
        min_args = 3 if name == "_ui_copy" else 2
        if len(node.args) < min_args:
            continue
        if name == "_ui_copy":
            en_arg, zh_arg = node.args[1], node.args[2]
        else:
            en_arg, zh_arg = node.args[0], node.args[1]
        if (
            isinstance(en_arg, ast.Constant)
            and isinstance(zh_arg, ast.Constant)
            and isinstance(en_arg.value, str)
            and isinstance(zh_arg.value, str)
        ):
            keys.add(_copy_key(en_arg.value, zh_arg.value))
    return keys


def test_webui_copy_catalog_covers_all_static_translation_pairs() -> None:
    expected: set[str] = set()
    for path in WEBUI_DIR.glob("*.py"):
        if path.name in {"copy_catalog.py"}:
            continue
        expected |= _extract_expected_keys(path)

    missing = sorted(k for k in expected if k not in WEBUI_COPY_CATALOG)
    assert missing == [], f"Missing copy keys in catalog: {missing[:20]}"
