"""
Protocol events, with Delimited against the echo server of conftest.py

Protocol and adapter events come through the same callbacks, in the order they happened
"""

import asyncio
import time

import pytest

from syndesi import IP, AsyncDelimited, AsyncIP, Delimited
from syndesi.adapters.events import AdapterFrameEvent, AdapterWriteEvent
from syndesi.protocols.protocol import (
    ProtocolBufferEvent,
    ProtocolDecodeErrorEvent,
    ProtocolEngine,
    ProtocolFrameEvent,
    ProtocolReadEvent,
    ProtocolWriteEvent,
)
from syndesi.tools.errors import ProtocolReadError

HOST = "127.0.0.1"


def wait_for(condition, timeout: float = 2.0) -> None:
    """Events are emitted on the reactor thread, give it the time to get there"""
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not met in time"
        time.sleep(0.01)


def of_type(events, event_type):
    return [event for event in events if isinstance(event, event_type)]


@pytest.fixture
def delimited(port):
    delimited = Delimited(IP(HOST, port=port))
    yield delimited
    delimited.close()


@pytest.fixture
def events(delimited):
    events = []
    delimited.register_event_callback(events.append)
    return events


def test_query(delimited, events):
    assert delimited.query("hello") == "hello"

    kinds = [type(event) for event in events]
    # Encoded, then written. Assembled by the adapter, then by the protocol
    assert kinds.index(ProtocolWriteEvent) < kinds.index(AdapterWriteEvent)
    assert kinds.index(AdapterFrameEvent) < kinds.index(ProtocolFrameEvent)
    assert kinds.index(ProtocolFrameEvent) < kinds.index(ProtocolReadEvent)

    (write,) = of_type(events, ProtocolWriteEvent)
    assert write.payload == "hello"
    (adapter_frame,) = of_type(events, AdapterFrameEvent)
    (frame,) = of_type(events, ProtocolFrameEvent)
    assert frame.frame.data == "hello"
    assert frame.adapter_frame_ids == [adapter_frame.frame.id]
    (read,) = of_type(events, ProtocolReadEvent)
    # The echo can be faster than the read that follows the write
    assert read.frame is frame.frame and read.from_buffer == frame.buffered


def test_buffer(delimited, events):
    delimited.write("A")
    delimited.write("B")
    wait_for(lambda: len(of_type(events, ProtocolBufferEvent)) == 2)
    first, second = (event.frame for event in of_type(events, ProtocolFrameEvent))
    assert [e.added_frame_ids for e in of_type(events, ProtocolBufferEvent)] == [
        [first.id],
        [second.id],
    ]

    assert delimited.read() == "A"
    assert of_type(events, ProtocolBufferEvent)[-1].removed_frame_ids == [first.id]
    assert of_type(events, ProtocolReadEvent)[-1].from_buffer

    delimited.clear_buffer()
    wait_for(lambda: len(of_type(events, ProtocolBufferEvent)) == 4)
    assert of_type(events, ProtocolBufferEvent)[-1].removed_frame_ids == [second.id]


def test_full_buffer(port, monkeypatch):
    monkeypatch.setattr(ProtocolEngine, "_FRAME_BUFFER_MAX", 1)
    delimited = Delimited(IP(HOST, port=port))
    events = []
    delimited.register_event_callback(events.append)

    delimited.write("A")
    wait_for(lambda: of_type(events, ProtocolFrameEvent))
    delimited.write("B")  # pushes A out
    wait_for(lambda: len(of_type(events, ProtocolFrameEvent)) == 2)
    a, b = (event.frame for event in of_type(events, ProtocolFrameEvent))
    assert of_type(events, ProtocolBufferEvent)[-1].removed_frame_ids == [a.id]

    delimited.adapter.write(b"\xff\n")  # a decode error pushes B out
    wait_for(lambda: len(of_type(events, ProtocolBufferEvent)) == 3)
    assert of_type(events, ProtocolBufferEvent)[-1].removed_frame_ids == [b.id]
    delimited.close()


def test_decode_error(delimited, events):
    delimited.adapter.write(b"\xff\n")
    with pytest.raises(ProtocolReadError):
        delimited.read()
    (error,) = of_type(events, ProtocolDecodeErrorEvent)
    assert "Cannot decode" in str(error.error)


def test_clear_event_callbacks(delimited, events):
    delimited.clear_event_callbacks()
    delimited.query("hello")
    assert events == []


def test_failing_callback(delimited, events):
    def fail(event):
        raise RuntimeError("bug in the callback")

    delimited.register_event_callback(fail)
    assert delimited.query("hello") == "hello"
    assert of_type(events, ProtocolReadEvent)  # the other callbacks still run


def test_async(port):
    async def main():
        events = []
        async with AsyncDelimited(AsyncIP(HOST, port=port)) as delimited:
            await delimited.register_event_callback(events.append)
            assert await delimited.query("hello") == "hello"
            await delimited.clear_event_callbacks()
            await delimited.query("hello")
        return events

    events = asyncio.run(main())
    assert len(of_type(events, ProtocolReadEvent)) == 1
