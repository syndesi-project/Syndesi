"""
Delimited protocol tests, against a local TCP server sending back what it receives
"""

import asyncio
import socket
import socketserver
import threading

import pytest

from syndesi import IP, AsyncDelimited, AsyncIP, Delimited
from syndesi.adapters.stop_conditions import Continuation, Termination
from syndesi.protocols.delimited import DelimitedCodec
from syndesi.tools.errors import AdapterOpenError, ProtocolReadError

HOST = "127.0.0.1"


class _Echo(socketserver.BaseRequestHandler):
    def handle(self):
        while data := self.request.recv(4096):
            self.request.sendall(data)


@pytest.fixture(scope="module")
def port():
    """Port of a TCP server sending back everything it receives"""
    server = socketserver.ThreadingTCPServer((HOST, 0), _Echo)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def _closed_port() -> int:
    """Return a local TCP port nobody listens on"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


# Codec, no I/O


def test_codec():
    codec = DelimitedCodec("\n", "\r\n", "utf-8", format_response=True)
    assert codec.encode("*IDN?") == b"*IDN?\n"
    assert codec.decode(b"ABC\r\n") == "ABC"
    assert codec.decode(b"ABC") == "ABC"


def test_codec_keep_termination():
    codec = DelimitedCodec("\n", "\n", "utf-8", format_response=False)
    assert codec.decode(b"ABC\n") == "ABC\n"


# A new Termination on every call, a stop-condition holds the state of a read
def test_codec_stop_conditions():
    codec = DelimitedCodec("\n", "\r\n", "utf-8", format_response=True)
    (first,), (second,) = codec.stop_conditions, codec.stop_conditions
    assert isinstance(first, Termination) and first.sequence == b"\r\n"
    assert first is not second


# Sync


def test_query(port):
    with Delimited(IP(HOST, port=port)) as delimited:
        assert delimited.query("hello") == "hello"


# Two lines in a single TCP segment are two frames
def test_two_lines(port):
    delimited = Delimited(IP(HOST, port=port))
    delimited.adapter.write(b"A\nB\n")
    assert delimited.read() == "A"
    assert delimited.read() == "B"
    delimited.close()


def test_bytes_termination(port):
    delimited = Delimited(IP(HOST, port=port), termination=b"\r\n")
    assert delimited.termination == "\r\n"
    assert delimited.query("hello") == "hello"
    delimited.close()


def test_timeout(port):
    # No timeout given to the adapter : the protocol one
    assert Delimited(IP(HOST, port=port, auto_open=False)).timeout == 2.0
    # The adapter one is kept
    assert Delimited(IP(HOST, port=port, timeout=0.5, auto_open=False)).timeout == 0.5
    # Unless the protocol is given one
    assert Delimited(IP(HOST, port=port, timeout=0.5, auto_open=False), timeout=3).timeout == 3


def test_adapter_stop_conditions_replaced(port):
    adapter = IP(HOST, port=port, stop_conditions=Continuation(0.1), auto_open=False)
    Delimited(adapter, "\r")
    (stop_condition,) = adapter.stop_conditions
    assert isinstance(stop_condition, Termination) and stop_condition.sequence == b"\r"


def test_set_termination(port):
    delimited = Delimited(IP(HOST, port=port))
    delimited.set_termination("\r")
    assert delimited.termination == delimited.receive_termination == "\r"
    assert delimited.query("hello") == "hello"
    delimited.close()


# A frame that can't be decoded fails its read, not the protocol
def test_decode_error(port):
    delimited = Delimited(IP(HOST, port=port))
    delimited.adapter.write(b"\xff\n")
    with pytest.raises(ProtocolReadError):
        delimited.read()
    assert delimited.query("hello") == "hello"
    delimited.close()


# Async


def test_async_query(port):
    async def main():
        async with AsyncDelimited(AsyncIP(HOST, port=port)) as delimited:
            return await delimited.query("hello")

    assert asyncio.run(main()) == "hello"


def test_async_set_termination(port):
    async def main():
        async with AsyncDelimited(AsyncIP(HOST, port=port)) as delimited:
            await delimited.set_termination("\r")
            return await delimited.query("hello")

    assert asyncio.run(main()) == "hello"


# A read cancelled by asyncio must free the read slot of the adapter engine
def test_async_cancelled_read(port):
    async def main():
        async with AsyncDelimited(AsyncIP(HOST, port=port)) as delimited:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(delimited.read(timeout=None), 0.2)
            return await delimited.query("hello")

    assert asyncio.run(main()) == "hello"


# The adapter open submitted at construction fails, the protocol must raise its error
def test_async_open_error():
    async def main():
        delimited = AsyncDelimited(AsyncIP(HOST, port=_closed_port()))
        with pytest.raises(AdapterOpenError):
            await delimited.query("hello")

    asyncio.run(main())
