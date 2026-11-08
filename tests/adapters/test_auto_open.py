"""
Auto-open rules (see AdapterEngine) :

1. The first write, or read that needs the target, opens it
2. An explicit open() is always possible, to fail early
3. A failed implicit open is raised by the operation, and retried by the next one
4. Once closed (explicitly, or because the target went away), never reopened implicitly
5. auto_open=False (adapter or protocol) : never opened implicitly
"""

import asyncio
import socket
import threading
import time

import pytest

from syndesi import IP, AsyncIP, Delimited, Modbus
from syndesi.adapters.stop_conditions import Continuation
from syndesi.tools.errors import AdapterError, AdapterOpenError

HOST = "127.0.0.1"


class EchoServer:
    """
    Local TCP server that echoes what it receives, one client at a time

    greeting is sent to every client as soon as it connects, which lets a test read
    without writing first
    """

    def __init__(self, port: int = 0, greeting: bytes = b"") -> None:
        self._greeting = greeting
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((HOST, port))
        self._sock.listen(4)
        self._sock.settimeout(0.1)
        self.port: int = self._sock.getsockname()[1]
        self.connections = 0
        self._clients: list[socket.socket] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                client, _ = self._sock.accept()
            except (TimeoutError, OSError):
                continue
            self.connections += 1
            self._clients.append(client)
            threading.Thread(target=self._serve, args=(client,), daemon=True).start()

    def _serve(self, client: socket.socket) -> None:
        try:
            if self._greeting:
                client.sendall(self._greeting)
            while data := client.recv(1024):
                client.sendall(data)
        except OSError:
            pass

    def drop_clients(self) -> None:
        """Close every client connection, as a target going away would"""
        for client in self._clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()
        self._clients.clear()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()
        self.drop_clients()
        self._sock.close()


@pytest.fixture
def server():
    s = EchoServer()
    yield s
    s.stop()


def _client(port: int | None, **kwargs) -> IP:
    return IP(HOST, port=port, timeout=1, stop_conditions=Continuation(0.05), **kwargs)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


# ┌─────────────────────────┐
# │ 1. Open on first use     │
# └─────────────────────────┘


def test_not_opened_at_construction(server):
    client = _client(server.port)
    time.sleep(0.1)
    assert not client.is_open
    assert server.connections == 0
    client.close()


def test_write_opens(server):
    client = _client(server.port)
    assert client.query(b"abc") == b"abc"
    assert client.is_open
    client.close()


def test_read_opens(server):
    greeting_server = EchoServer(greeting=b"hello")
    try:
        client = _client(greeting_server.port)
        assert client.read() == b"hello"
        assert client.is_open
        client.close()
    finally:
        greeting_server.stop()


# The port is only known once a protocol (or a driver) sets it after construction
def test_default_port_set_after_construction(server):
    client = _client(None)
    assert not client.is_open
    client.set_default_port(server.port)
    assert client.query(b"abc") == b"abc"
    client.close()


def test_incomplete_descriptor_raises_on_first_use():
    client = _client(None)
    with pytest.raises(AdapterOpenError, match="incomplete"):
        client.write(b"abc")


# A protocol read, with nothing written first, opens the adapter too
def test_protocol_read_opens():
    greeting_server = EchoServer(greeting=b"hello\n")
    try:
        protocol = Delimited(_client(greeting_server.port))
        assert protocol.read() == "hello"
        assert protocol.is_open
        protocol.close()
    finally:
        greeting_server.stop()


def test_protocol_query_opens(server):
    protocol = Delimited(_client(server.port))
    assert protocol.query("abc") == "abc"
    protocol.close()


# ┌─────────────────────────┐
# │ 2. Explicit open         │
# └─────────────────────────┘


def test_explicit_open(server):
    client = _client(server.port)
    client.open()
    assert client.is_open
    assert server.connections == 1 or _wait_for(lambda: server.connections == 1)
    assert client.query(b"abc") == b"abc"
    client.close()


def test_explicit_open_fails_early():
    client = _client(_free_port())
    with pytest.raises(AdapterOpenError):
        client.open()


# ┌─────────────────────────┐
# │ 3. Failed open, retried  │
# └─────────────────────────┘


def test_failed_open_is_retried():
    port = _free_port()
    client = _client(port)
    with pytest.raises(AdapterOpenError):
        client.write(b"abc")

    late_server = EchoServer(port=port)
    try:
        assert client.query(b"abc") == b"abc"
        client.close()
    finally:
        late_server.stop()


# ┌─────────────────────────┐
# │ 4. No implicit reopen    │
# └─────────────────────────┘


def test_no_reopen_after_close(server):
    client = _client(server.port)
    assert client.query(b"abc") == b"abc"
    client.close()
    with pytest.raises(AdapterError):
        client.write(b"abc")
    assert not client.is_open

    client.open()
    assert client.query(b"abc") == b"abc"
    client.close()


def test_close_before_use_disables_auto_open(server):
    client = _client(server.port)
    client.close()
    with pytest.raises(AdapterError):
        client.write(b"abc")
    assert server.connections == 0


def test_no_reopen_after_target_disconnect(server):
    client = _client(server.port)
    assert client.query(b"abc") == b"abc"
    server.drop_clients()
    assert _wait_for(lambda: not client.is_open)
    with pytest.raises(AdapterError):
        client.write(b"abc")
    assert server.connections == 1


# ┌─────────────────────────┐
# │ 5. auto_open=False       │
# └─────────────────────────┘


def test_adapter_auto_open_false(server):
    client = _client(server.port, auto_open=False)
    with pytest.raises(AdapterError):
        client.write(b"abc")
    with pytest.raises(AdapterError):
        client.read()
    assert server.connections == 0
    client.open()
    assert client.query(b"abc") == b"abc"
    client.close()


def test_protocol_auto_open_false(server):
    adapter = _client(None)
    modbus = Modbus(adapter, auto_open=False)
    adapter.descriptor.port = server.port  # the echo server, instead of 502
    with pytest.raises(AdapterError, match="not open"):
        modbus.read_holding_registers(1, 1)
    assert server.connections == 0
    modbus.open()
    assert modbus.is_open
    assert _wait_for(lambda: server.connections == 1)
    modbus.close()


# The protocol can only take auto-open away, not give back what the adapter refused
def test_protocol_auto_open_true_keeps_adapter_false(server):
    protocol = Delimited(_client(server.port, auto_open=False))  # protocol default : True
    with pytest.raises(AdapterError):
        protocol.write("abc")
    assert server.connections == 0


# ┌─────────────────────────┐
# │ Modbus                   │
# └─────────────────────────┘


def test_modbus_sets_port_before_open():
    adapter = IP(HOST)
    Modbus(adapter)
    assert adapter.descriptor.port == 502
    assert not adapter.is_open


def test_modbus_auto_open_false():
    adapter = IP(HOST, port=_free_port())
    modbus = Modbus(adapter, auto_open=False)
    with pytest.raises(AdapterError, match="not open"):
        modbus.read_holding_registers(1, 1)


# ┌─────────────────────────┐
# │ Async                    │
# └─────────────────────────┘


def test_async_first_operation_opens(server):
    async def main():
        client = AsyncIP(HOST, port=server.port, timeout=1, stop_conditions=Continuation(0.05))
        await asyncio.sleep(0.1)
        assert not client.is_open
        data = await client.query(b"abc")
        assert client.is_open
        await client.close()
        return data

    assert asyncio.run(main()) == b"abc"


def test_async_failed_open_raised_by_operation():
    async def main():
        client = AsyncIP(HOST, port=_free_port(), timeout=1)
        with pytest.raises(AdapterOpenError):
            await client.write(b"abc")

    asyncio.run(main())


def _wait_for(condition, timeout: float = 2.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if condition():
            return True
        time.sleep(0.01)
    return condition()
