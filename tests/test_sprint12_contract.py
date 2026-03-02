import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from nanobot.agent.loop import AgentLoop
from nanobot.agent.tools.message import MessageTool
from nanobot.bus.queue import MessageBus
from nanobot.channels.base import BaseChannel
from nanobot.channels.telegram import TelegramChannel
from nanobot.config.schema import TelegramConfig


@dataclass
class _DummyConfig:
    allow_from: list[str]


class _DummyChannel(BaseChannel):
    name = "dummy"

    async def start(self) -> None:  # pragma: no cover
        self._running = True

    async def stop(self) -> None:  # pragma: no cover
        self._running = False

    async def send(self, msg) -> None:  # pragma: no cover
        _ = msg


@pytest.mark.asyncio
async def test_base_channel_derives_attachments_from_media() -> None:
    bus = MessageBus()
    bus.publish_inbound = AsyncMock()  # type: ignore[method-assign]
    channel = _DummyChannel(_DummyConfig(allow_from=[]), bus)

    await channel._handle_message(
        sender_id="u1",
        chat_id="c1",
        content="hello",
        media=["/tmp/example.txt"],
        attachments=None,
    )

    bus.publish_inbound.assert_awaited_once()
    inbound = bus.publish_inbound.await_args.args[0]
    assert inbound.media == ["/tmp/example.txt"]
    assert inbound.attachments == [{"path": "/tmp/example.txt"}]


@pytest.mark.asyncio
async def test_message_tool_normalizes_attachments_and_reply_target() -> None:
    sent = []

    async def _send(msg):
        sent.append(msg)

    tool = MessageTool(
        send_callback=_send,
        default_channel="telegram",
        default_chat_id="42",
        default_message_id="9001",
    )

    result = await tool.execute(
        content="done",
        attachments=[{"path": "/tmp/report.pdf", "name": "report.pdf"}],
    )

    assert "with 1 attachments" in result
    outbound = sent[-1]
    assert outbound.reply_to == "9001"
    assert outbound.media == ["/tmp/report.pdf"]
    assert outbound.attachments == [{"path": "/tmp/report.pdf", "name": "report.pdf"}]


@pytest.mark.asyncio
async def test_message_tool_prefers_explicit_reply_to_over_message_id() -> None:
    sent = []

    async def _send(msg):
        sent.append(msg)

    tool = MessageTool(send_callback=_send, default_channel="telegram", default_chat_id="42")
    await tool.execute(content="x", message_id="100", reply_to="200")

    assert sent[-1].reply_to == "200"


@pytest.mark.asyncio
async def test_message_tool_applies_output_sanitizer() -> None:
    sent = []

    async def _send(msg):
        sent.append(msg)

    tool = MessageTool(
        send_callback=_send,
        output_sanitizer=lambda text: text.replace("Calling doc_read function with parameters:", ""),
        default_channel="telegram",
        default_chat_id="42",
    )
    await tool.execute(content="Calling doc_read function with parameters: {\"x\":1}")

    assert "Calling doc_read function with parameters:" not in sent[-1].content


def test_agent_loop_reply_resolution_prefers_reply_to_field() -> None:
    value = AgentLoop._resolve_reply_to({"message_id": "100", "reply_to": "200"})
    assert value == "200"


class _DummyQuery:
    def __init__(self, data: str, message) -> None:
        self.data = data
        self.message = message
        self.answers: list[tuple[str, bool]] = []

    async def answer(self, text: str, show_alert: bool = False) -> None:
        self.answers.append((text, show_alert))


class _DummyUpdate:
    def __init__(self, query: _DummyQuery, user) -> None:
        self.callback_query = query
        self.effective_user = user


@pytest.mark.asyncio
async def test_telegram_callback_token_is_one_time_and_routes_reply_to() -> None:
    channel = TelegramChannel(
        config=TelegramConfig(token="dummy", inline_actions=True, callback_ttl_seconds=60),
        bus=MessageBus(),
    )

    captured: dict = {}

    async def _fake_handle_message(**kwargs):
        captured.update(kwargs)

    channel._handle_message = _fake_handle_message  # type: ignore[method-assign]

    markup = channel._build_inline_keyboard(
        actions=[{"id": "opt_a", "title": "Option A", "value": "A", "prompt": "/run a"}],
        chat_id="123",
    )
    assert markup is not None
    callback_data = markup.inline_keyboard[0][0].callback_data
    assert callback_data and callback_data.startswith("nb:")

    message = SimpleNamespace(chat_id=123, message_id=888, chat=SimpleNamespace(type="private"))
    user = SimpleNamespace(id=1173477546, username="tester", first_name="Tester")
    first = _DummyUpdate(_DummyQuery(callback_data, message), user)

    await channel._on_callback_query(first, None)
    await asyncio.sleep(0)

    assert captured.get("chat_id") == "123"
    assert captured.get("content") == "/run a"
    assert captured.get("metadata", {}).get("reply_to") == 888
    assert captured.get("metadata", {}).get("callback_action", {}).get("id") == "opt_a"

    second = _DummyUpdate(_DummyQuery(callback_data, message), user)
    await channel._on_callback_query(second, None)
    assert second.callback_query.answers
    assert "expired" in second.callback_query.answers[0][0].lower()
