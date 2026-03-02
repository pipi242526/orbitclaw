from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from orbitclaw.agent.loop import AgentLoop
from orbitclaw.bus.events import InboundMessage
from orbitclaw.bus.queue import MessageBus
from orbitclaw.providers.base import LLMProvider, LLMResponse


class _FixedResponseProvider(LLMProvider):
    def __init__(self, response: LLMResponse):
        super().__init__(api_key=None, api_base=None)
        self._response = response

    async def chat(self, messages, tools=None, model=None, max_tokens=4096, temperature=0.7) -> LLMResponse:
        _ = (messages, tools, model, max_tokens, temperature)
        return self._response

    def get_default_model(self) -> str:
        return "test-model"


@pytest.mark.asyncio
async def test_final_reply_must_flow_through_policy_pipeline(tmp_path: Path) -> None:
    provider = _FixedResponseProvider(
        LLMResponse(content='Calling doc_read function with parameters: {"file_path":"a.pdf"}')
    )
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
    )
    loop.policy.enforce_final_reply = AsyncMock(return_value="clean-final")  # type: ignore[method-assign]

    out = await loop.process_direct("hello", session_key="cli:cov", channel="cli", chat_id="cov")
    assert out == "clean-final"
    loop.policy.enforce_final_reply.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_exception_reply_must_flow_through_policy_pipeline(tmp_path: Path) -> None:
    provider = _FixedResponseProvider(LLMResponse(content="ok"))
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
    )

    async def _raise(*args, **kwargs):
        _ = (args, kwargs)
        raise RuntimeError("boom")

    loop._process_message = _raise  # type: ignore[method-assign]
    loop.policy.format_user_error = MagicMock(return_value="formatted-error")  # type: ignore[method-assign]

    out = await loop.process_direct("hello", session_key="cli:cov-err", channel="cli", chat_id="cov-err")
    assert out == "formatted-error"
    loop.policy.format_user_error.assert_called_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_unknown_command_reply_uses_policy_formatter(tmp_path: Path) -> None:
    provider = _FixedResponseProvider(LLMResponse(content="unused"))
    loop = AgentLoop(
        bus=MessageBus(),
        provider=provider,
        workspace=tmp_path,
        model="test-model",
    )
    loop.policy.unknown_command_text = MagicMock(return_value="unknown-formatted")  # type: ignore[method-assign]

    msg = InboundMessage(channel="telegram", sender_id="u1", chat_id="c1", content="/no_such_command")
    out = await loop._process_message(msg, session_key="telegram:c1")
    assert out is not None
    assert out.content == "unknown-formatted"
    loop.policy.unknown_command_text.assert_called_once()  # type: ignore[attr-defined]
