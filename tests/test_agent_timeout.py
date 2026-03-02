from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orbitclaw.agent.loop import AgentLoop
from orbitclaw.bus.queue import MessageBus


@pytest.mark.asyncio
async def test_process_direct_returns_timeout_error_when_turn_exceeds_budget(tmp_path: Path) -> None:
    provider = MagicMock()
    provider.get_default_model.return_value = "test-model"
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
        turn_timeout_seconds=5,
    )

    async def _slow(*args, **kwargs):
        await asyncio.sleep(0.2)
        return None

    loop._process_message = _slow  # type: ignore[method-assign]
    loop._turn_timeout_seconds = 0.05
    text = await loop.process_direct("hello", session_key="cli:test", channel="cli", chat_id="test")
    assert "timed out" in text.lower()
