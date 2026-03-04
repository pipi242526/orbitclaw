"""HTTP adapter helpers for Mochat channel."""

from __future__ import annotations

from typing import Any


async def mochat_post_json(
    http_client: Any,
    *,
    base_url: str,
    claw_token: str,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Perform one Mochat API JSON request with common error handling."""
    url = f"{base_url.strip().rstrip('/')}{path}"
    response = await http_client.post(
        url,
        headers={
            "Content-Type": "application/json",
            "X-Claw-Token": claw_token,
        },
        json=payload,
    )
    if not response.is_success:
        raise RuntimeError(f"Mochat HTTP {response.status_code}: {response.text[:200]}")

    try:
        parsed = response.json()
    except Exception:
        parsed = response.text

    if isinstance(parsed, dict) and isinstance(parsed.get("code"), int):
        if parsed["code"] != 200:
            msg = str(parsed.get("message") or parsed.get("name") or "request failed")
            raise RuntimeError(f"Mochat API error: {msg} (code={parsed['code']})")
        data = parsed.get("data")
        return data if isinstance(data, dict) else {}
    return parsed if isinstance(parsed, dict) else {}


async def mochat_api_send(
    http_client: Any,
    *,
    base_url: str,
    claw_token: str,
    path: str,
    id_key: str,
    id_val: str,
    content: str,
    reply_to: str | None,
    group_id: str | None = None,
) -> dict[str, Any]:
    """Unified send helper for session and panel messages."""
    body: dict[str, Any] = {id_key: id_val, "content": content}
    if reply_to:
        body["replyTo"] = reply_to
    if group_id:
        body["groupId"] = group_id
    return await mochat_post_json(
        http_client,
        base_url=base_url,
        claw_token=claw_token,
        path=path,
        payload=body,
    )
