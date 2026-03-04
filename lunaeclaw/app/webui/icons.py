"""Inline SVG icon helpers for WebUI."""

from __future__ import annotations

from html import escape

_ICON_PATHS: dict[str, str] = {
    "copy": '<rect x="9" y="9" width="10" height="10" rx="2"></rect><path d="M7 15H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v1"></path>',
    "save": '<path d="M5 4h12l3 3v13H4V4h1z"></path><path d="M8 4v6h8V4"></path><path d="M8 20v-6h8v6"></path>',
    "delete": '<path d="M4 7h16"></path><path d="M9 7V5h6v2"></path><path d="M7 7l1 13h8l1-13"></path><path d="M10 11v6"></path><path d="M14 11v6"></path>',
    "add": '<path d="M12 5v14"></path><path d="M5 12h14"></path>',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.34-5.66"></path><path d="M20 4v6h-6"></path>',
    "reset": '<path d="M4 12a8 8 0 1 0 2.34-5.66"></path><path d="M4 20v-6h6"></path>',
    "globe": '<circle cx="12" cy="12" r="9"></circle><path d="M3 12h18"></path><path d="M12 3a14 14 0 0 1 0 18"></path><path d="M12 3a14 14 0 0 0 0 18"></path>',
    "theme": '<circle cx="12" cy="12" r="9"></circle><path d="M12 3v18"></path>',
    "dashboard": '<rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1.8"></rect><rect x="13" y="3.5" width="7.5" height="5.2" rx="1.8"></rect><rect x="13" y="10.8" width="7.5" height="9.7" rx="1.8"></rect><rect x="3.5" y="13" width="7.5" height="7.5" rx="1.8"></rect>',
    "chat": '<path d="M5 6h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H10l-5 4v-4H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z"></path>',
    "model": '<ellipse cx="12" cy="6" rx="7" ry="3"></ellipse><path d="M5 6v5c0 1.66 3.13 3 7 3s7-1.34 7-3V6"></path><path d="M5 11v5c0 1.66 3.13 3 7 3s7-1.34 7-3v-5"></path>',
    "channels": '<path d="M5 8h8"></path><path d="M5 12h14"></path><path d="M5 16h10"></path><circle cx="17.5" cy="8" r="2.5"></circle>',
    "mcp": '<path d="M8 5h8l4 7-4 7H8l-4-7 4-7z"></path><path d="M12 9v6"></path><path d="M9.5 12h5"></path>',
    "skills": '<path d="M14.5 4.5 19.5 9.5 10 19l-5 .8.8-5 8.7-8.7z"></path><path d="M13 6l5 5"></path>',
    "media": '<rect x="3.5" y="5.5" width="17" height="13" rx="2"></rect><circle cx="9" cy="10" r="1.6"></circle><path d="m7 16 3.4-3.2 2.6 2.2 3.4-3 1.6 4"></path>',
    "send": '<path d="M4 12 20 4l-4 16-4.5-6z"></path><path d="M10 14 20 4"></path>',
    "import": '<path d="M12 3v11"></path><path d="m8 10 4 4 4-4"></path><path d="M4 20h16"></path>',
    "clear": '<path d="M4 7h16"></path><path d="M8 7V5h8v2"></path><path d="M7 7l1 13h8l1-13"></path>',
}


def icon_svg(name: str, *, title: str = "") -> str:
    """Return a small, themed inline SVG icon."""
    path = _ICON_PATHS.get(name, _ICON_PATHS["copy"])
    title_node = f"<title>{escape(title)}</title>" if title else ""
    return (
        '<span class="ui-icon" aria-hidden="true">'
        f'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        f'stroke-linecap="round" stroke-linejoin="round">{title_node}{path}</svg>'
        "</span>"
    )


def logo_svg(*, title: str = "OrbitClaw") -> str:
    """Return brand logo mark SVG."""
    title_node = f"<title>{escape(title)}</title>" if title else ""
    return (
        '<span class="brand-logo" aria-hidden="true">'
        '<svg viewBox="0 0 56 56" fill="none">'
        f"{title_node}"
        '<defs><linearGradient id="oc-g" x1="8" y1="6" x2="46" y2="50" gradientUnits="userSpaceOnUse">'
        '<stop stop-color="#49A1FF"></stop><stop offset="1" stop-color="#1E63FF"></stop>'
        "</linearGradient></defs>"
        '<rect x="4.5" y="4.5" width="47" height="47" rx="14" fill="url(#oc-g)"></rect>'
        '<path d="M16 30c0-7.2 5.8-13 13-13 5 0 9.5 2.8 11.7 7.2" stroke="white" stroke-width="3.6" stroke-linecap="round"></path>'
        '<path d="M39.5 19.5 42 28l-8.5-2.5" stroke="white" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"></path>'
        '<circle cx="25" cy="33" r="3.3" fill="white"></circle>'
        '<path d="M30.5 36.5 35 41" stroke="white" stroke-width="3.2" stroke-linecap="round"></path>'
        '<path d="M20 41.2c3.2 2.2 7 3.3 11 3.3" stroke="white" stroke-opacity=".9" stroke-width="2.8" stroke-linecap="round"></path>'
        "</svg>"
        "</span>"
    )
