"""HTML helpers for WebUI rendering."""

from __future__ import annotations

from html import escape as _escape
from typing import Any


def escape(value: Any, quote: bool = True) -> str:
    """Escape arbitrary values for HTML output without type errors."""
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    return _escape(text, quote=quote)
