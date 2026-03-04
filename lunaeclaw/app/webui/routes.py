"""GET route dispatch for WebUI."""

from __future__ import annotations

from typing import Any

from orbitclaw.app.webui.services import safe_positive_int

_GET_ROUTES: dict[str, str] = {
    "/": "_render_dashboard",
    "/chat": "_render_chat",
    "/endpoints": "_render_endpoints",
    "/channels": "_render_channels",
    "/mcp": "_render_mcp",
    "/skills": "_render_skills",
}


def dispatch_get_route(
    handler: Any,
    route_path: str,
    *,
    params: dict[str, list[str]],
    msg: str,
    err: str,
) -> bool:
    if route_path == "/extensions":
        handler._redirect("/mcp", msg=msg, err=err)
        return True

    if route_path == "/media":
        media_page = safe_positive_int((params.get("media_page") or ["1"])[0], default=1)
        exports_page = safe_positive_int((params.get("exports_page") or ["1"])[0], default=1)
        handler._render_media(msg=msg, err=err, media_page=media_page, exports_page=exports_page)
        return True

    method_name = _GET_ROUTES.get(route_path)
    if not method_name:
        return False
    getattr(handler, method_name)(msg=msg, err=err)
    return True
