"""Pure mapping helpers for Mochat channel."""

from __future__ import annotations

from lunaeclaw.capabilities.channels.mochat_types import MochatBufferedEntry, MochatTarget


def resolve_mochat_target(raw: str) -> MochatTarget:
    """Resolve id and target kind from user-provided target string."""
    trimmed = (raw or "").strip()
    if not trimmed:
        return MochatTarget(id="", is_panel=False)

    lowered = trimmed.lower()
    cleaned, forced_panel = trimmed, False
    for prefix in ("mochat:", "group:", "channel:", "panel:"):
        if lowered.startswith(prefix):
            cleaned = trimmed[len(prefix) :].strip()
            forced_panel = prefix in {"group:", "channel:", "panel:"}
            break

    if not cleaned:
        return MochatTarget(id="", is_panel=False)
    return MochatTarget(id=cleaned, is_panel=forced_panel or not cleaned.startswith("session_"))


def resolve_require_mention(config: object, session_id: str, group_id: str) -> bool:
    """Resolve mention requirement for group/panel conversations."""
    groups = getattr(config, "groups", {}) or {}
    for key in (group_id, session_id, "*"):
        if key and key in groups:
            return bool(groups[key].require_mention)
    mention = getattr(config, "mention", None)
    return bool(getattr(mention, "require_in_groups", False))


def build_buffered_body(entries: list[MochatBufferedEntry], is_group: bool) -> str:
    """Build text body from one or more buffered entries."""
    if not entries:
        return ""
    if len(entries) == 1:
        return entries[0].raw_body
    lines: list[str] = []
    for entry in entries:
        if not entry.raw_body:
            continue
        if is_group:
            label = entry.sender_name.strip() or entry.sender_username.strip() or entry.author
            if label:
                lines.append(f"{label}: {entry.raw_body}")
                continue
        lines.append(entry.raw_body)
    return "\n".join(lines).strip()


def normalize_mochat_id_list(values: list[str]) -> tuple[list[str], bool]:
    """Normalize configured IDs and extract wildcard flag."""
    cleaned = [str(v).strip() for v in values if str(v).strip()]
    return sorted({v for v in cleaned if v != "*"}), "*" in cleaned


def read_mochat_group_id(metadata: dict[str, object]) -> str | None:
    """Read optional group id from outbound metadata."""
    if not isinstance(metadata, dict):
        return None
    value = metadata.get("group_id") or metadata.get("groupId")
    return value.strip() if isinstance(value, str) and value.strip() else None
