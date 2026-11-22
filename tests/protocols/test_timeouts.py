"""
Timeouts across the layers, and what a timeout reports

Rules :
- A protocol gives its timeout to the adapter, unless the user chose the adapter one
- A timeout chosen by the user (constructor or set_timeout) is never overridden
- A driver default (set_default_timeout) is adopted by the protocol built on top
- A timeout given to a read covers the whole exchange, first fragment included
- A timeout reports what arrived without forming a valid frame
"""

import asyncio
import socket
import threading
import time

import pytest

from syndesi import IP, SCPI, AsyncDelimited, AsyncIP, Delimited, Length, Termination
from syndesi.adapters.framer import AdapterReadFrame
from syndesi.protocols.modbus.backend import ModbusTCPBackend
from syndesi.errors import AdapterTimeoutError

HOST = "127.0.0.1"


def _server(reply: bytes | None) -> int:
    """Local TCP server answering every write with reply, or never if None"""
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((HOST, 0))
    listener.listen()

    def handle(client: socket.socket) -> None:
        with client:
            while client.recv(4096):
                if reply is not None:
                    client.sendall(reply)

    def accept() -> None:
        while True:
            client, _ = listener.accept()
            threading.Thread(target=handle, args=(client,), daemon=True).start()

    threading.Thread(target=accept, daemon=True).start()
    return listener.getsockname()[1]


@pytest.fixture(scope="module")
def silent():
    """Port of a device that never answers"""
    return _server(None)


@pytest.fixture(scope="module")
def partial():
    """Port of a device answering with \\r only, where \\n is expected"""
    return _server(b"OK\r")


# Who sets the adapter timeout


def test_protocol_gives_its_default_to_the_adapter(silent):
    assert SCPI(IP(HOST, silent, auto_open=False)).adapter.timeout == 5.0
    assert Delimited(IP(HOST, silent, auto_open=False)).adapter.timeout == 2.0


def test_protocol_gives_its_explicit_timeout_to_the_adapter(silent):
    delimited = Delimited(IP(HOST, silent, auto_open=False), timeout=3)
    assert delimited.timeout == 3
    assert delimited.adapter.timeout == 3


def test_user_adapter_timeout_is_kept(silent):
    delimited = Delimited(IP(HOST, silent, timeout=0.5, auto_open=False), timeout=3)
    assert delimited.timeout == 3
    assert delimited.adapter.timeout == 0.5


def test_driver_default_is_adopted_by_the_protocol(silent):
    adapter = IP(HOST, silent, auto_open=False)
    adapter.set_default_timeout(4)
    assert not adapter.has_default_timeout
    delimited = Delimited(adapter)
    assert delimited.timeout == 4
    assert adapter.timeout == 4


def test_set_timeout_is_a_user_choice(silent):
    adapter = IP(HOST, silent, auto_open=False)
    adapter.set_timeout(0.5)
    adapter.set_default_timeout(3)
    assert adapter.timeout == 0.5
    assert Delimited(adapter).adapter.timeout == 0.5


def test_protocol_set_timeout_reaches_the_adapter(silent):
    delimited = SCPI(IP(HOST, silent, auto_open=False))
    delimited.set_timeout(7)
    assert delimited.timeout == 7
    assert delimited.adapter.timeout == 7


def test_protocol_set_timeout_keeps_user_adapter_timeout(silent):
    delimited = SCPI(IP(HOST, silent, timeout=0.5, auto_open=False))
    delimited.set_timeout(7)
    assert delimited.timeout == 7
    assert delimited.adapter.timeout == 0.5


def test_async_protocol_set_timeout_reaches_the_adapter(silent):
    async def main() -> None:
        # The async constructor doesn't wait for its configuration, the commands run in
        # order : the one of set_timeout comes after the protocol default
        delimited = AsyncDelimited(AsyncIP(HOST, silent, auto_open=False))
        await delimited.set_timeout(7)
        assert delimited.adapter.timeout == 7

    asyncio.run(main())


# Effective timeouts, against a device that never answers


def test_protocol_timeout_applies(silent):
    with Delimited(IP(HOST, silent), timeout=0.3) as delimited:
        with pytest.raises(AdapterTimeoutError) as error:
            delimited.query("x")
    assert error.value.timeout == 0.3
    assert error.value.received is None


def test_read_timeout_covers_the_first_fragment(silent):
    # The adapter would give up after 0.2 s, the read asks for longer
    with Delimited(IP(HOST, silent, timeout=0.2)) as delimited:
        start = time.monotonic()
        with pytest.raises(AdapterTimeoutError) as error:
            delimited.query("x", timeout=0.6)
        assert time.monotonic() - start >= 0.55
    assert error.value.timeout == 0.6


def test_user_adapter_timeout_ends_the_wait(silent):
    with Delimited(IP(HOST, silent, timeout=0.2), timeout=3) as delimited:
        with pytest.raises(AdapterTimeoutError) as error:
            delimited.query("x")
    # Reported with the timeout that expired, not the protocol one
    assert error.value.timeout == 0.2


# What a timeout reports, against a device answering without the expected terminator


def test_protocol_timeout_reports_received_data(partial):
    with Delimited(IP(HOST, partial), timeout=0.3) as delimited:
        with pytest.raises(AdapterTimeoutError) as error:
            delimited.query("x")
    assert error.value.received == b"OK\r"
    message = str(error.value)
    assert "b'OK\\r'" in message
    assert "Termination(b'\\n')" in message


@pytest.mark.parametrize("stop_condition", [Termination(b"\n"), Length(10)])
def test_adapter_timeout_reports_received_data(partial, stop_condition):
    with IP(HOST, partial, timeout=0.3, stop_conditions=stop_condition) as adapter:
        with pytest.raises(AdapterTimeoutError) as error:
            adapter.query(b"x")
    assert error.value.received == b"OK\r"
    assert str(stop_condition) in str(error.value)


def test_modbus_backend_pending_data():
    backend = ModbusTCPBackend()
    assert backend.pending_data is None
    # The start of an MBAP header : not enough to know the length of the frame
    backend.push(
        AdapterReadFrame(
            data=b"\x00\x01\x00",
            id=0,
            stop_timestamp=0.0,
            stop_condition=None,
            first_fragment_timestamp=0.0,
            response_delay=float("nan"),
        )
    )
    assert backend.pending_data == b"\x00\x01\x00"


def test_error_message():
    assert str(AdapterTimeoutError(1.0)) == (
        "No response received from target within 1.0 seconds"
    )
    message = str(AdapterTimeoutError(2.0, b"A" * 100, "Termination(b'\\n')"))
    assert message.startswith("No valid frame received within 2.0 seconds")
    assert "(100 bytes)" in message
    assert "..." in message
    assert message.endswith("waiting for Termination(b'\\n')")
