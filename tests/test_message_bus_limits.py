import pytest

from orbitclaw.bus.events import InboundMessage, OutboundMessage
from orbitclaw.bus.queue import MessageBus


@pytest.mark.asyncio
async def test_outbound_progress_message_dropped_when_queue_full() -> None:
    bus = MessageBus(outbound_maxsize=1)
    await bus.publish_outbound(OutboundMessage(channel="cli", chat_id="1", content="final"))
    assert bus.outbound_size == 1

    await bus.publish_outbound(
        OutboundMessage(
            channel="cli",
            chat_id="1",
            content="processing",
            metadata={"_progress": True},
        )
    )
    assert bus.outbound_size == 1
    kept = await bus.consume_outbound()
    assert kept.content == "final"


@pytest.mark.asyncio
async def test_outbound_non_progress_evicts_oldest_after_wait_timeout() -> None:
    bus = MessageBus(outbound_maxsize=1, outbound_full_wait_seconds=0.01)
    await bus.publish_outbound(OutboundMessage(channel="cli", chat_id="1", content="first"))
    await bus.publish_outbound(OutboundMessage(channel="cli", chat_id="1", content="second"))
    kept = await bus.consume_outbound()
    assert kept.content == "second"
    assert bus.outbound_dropped == 1


@pytest.mark.asyncio
async def test_inbound_drop_oldest_when_queue_full() -> None:
    bus = MessageBus(inbound_maxsize=1, inbound_overflow_policy="drop_oldest")
    await bus.publish_inbound(InboundMessage(channel="telegram", sender_id="u1", chat_id="c", content="first"))
    await bus.publish_inbound(InboundMessage(channel="telegram", sender_id="u1", chat_id="c", content="second"))
    kept = await bus.consume_inbound()
    assert kept.content == "second"
    assert bus.inbound_dropped == 1
