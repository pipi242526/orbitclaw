"""Generic tool alias support."""

from typing import Any

from loguru import logger

from lunaeclaw.capabilities.tools.base import Tool


class ToolAlias(Tool):
    """Expose an existing tool under a different name."""

    def __init__(self, alias_name: str, target_name: str, delegate: Tool):
        self._alias_name = alias_name
        self._target_name = target_name
        self._delegate = delegate

    @property
    def name(self) -> str:
        return self._alias_name

    @property
    def description(self) -> str:
        base = self._delegate.description or self._target_name
        return f"(alias of {self._target_name}) {base}"

    @property
    def parameters(self) -> dict[str, Any]:
        return self._delegate.parameters

    async def execute(self, **kwargs: Any) -> str:
        return await self._delegate.execute(**kwargs)


def install_tool_aliases(registry: Any, aliases: dict[str, str] | None) -> dict[str, list[str]]:
    """
    Install configured tool aliases into a registry.

    Returns a summary dict with keys: installed, skipped, unresolved.
    """
    summary: dict[str, list[str]] = {"installed": [], "skipped": [], "unresolved": []}
    if not aliases:
        return summary

    for raw_alias, raw_target in aliases.items():
        alias_name = (raw_alias or "").strip()
        target_name = (raw_target or "").strip()

        if not alias_name or not target_name:
            summary["skipped"].append(f"{raw_alias!r}->{raw_target!r}")
            continue
        if alias_name == target_name:
            summary["skipped"].append(f"{alias_name}->{target_name}")
            continue

        delegate = registry.get(target_name)
        if not delegate:
            summary["unresolved"].append(f"{alias_name}->{target_name}")
            continue

        registry.register(ToolAlias(alias_name=alias_name, target_name=target_name, delegate=delegate))
        summary["installed"].append(f"{alias_name}->{target_name}")
        logger.debug("Tool alias registered: '{}' -> '{}'", alias_name, target_name)

    return summary
