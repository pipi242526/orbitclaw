"""POST handler dispatch for WebUI."""

from __future__ import annotations

from typing import Any


_POST_ROUTES: dict[str, str] = {
    "/endpoints": "_handle_post_endpoints",
    "/channels": "_handle_post_channels",
    "/mcp": "_handle_post_mcp",
    "/skills": "_handle_post_skills",
    "/extensions": "_handle_post_mcp",
    "/media": "_handle_post_media",
}


def dispatch_post_route(handler: Any, route_path: str, form: dict[str, list[str]]) -> bool:
    method_name = _POST_ROUTES.get(route_path)
    if not method_name:
        return False
    getattr(handler, method_name)(form)
    return True

