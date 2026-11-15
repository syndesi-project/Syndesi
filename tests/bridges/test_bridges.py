"""
Bridges : I2C, SPI and SerialPort provided by a driver

The board is faked by a TCP server speaking a line protocol, the bridge driver talks to
it through Delimited(IP(...)), the way a custom board on a serial port would be used
"""

import asyncio
import inspect
import gc
import socketserver
import threading
import time

import pytest

from syndesi import (
    I2C,
    IP,
    SPI,
    Adapter,
    AsyncI2C,
    AsyncSPI,
    Delimited,
    Driver,
    I2CBridge,
    I2CTransfer,
    SerialBridge,
    SerialPort,
    SPIBridge,
    Termination,
)
from syndesi.adapters.events import AdapterEvent, AdapterReadEvent, AdapterWriteEvent
from syndesi.adapters.i2c import I2CDescriptor
from syndesi.tools.errors import AdapterOpenError, AdapterReadError, AdapterWriteError

NACK_ADDRESS = 0x7F

# ┌────────────┐
# │ Fake board │
# └────────────┘


class BoardState:
    """What the fake board remembers, shared by every connection"""

    def __init__(self) -> None:
        self.memory: dict[int, bytearray] = {}
        self.pointer: dict[int, int] = {}
        self.uart_rx = bytearray()
        self.uart_config: tuple[str, ...] | None = None
        self.lock = threading.Lock()

    def handle(self, line: str) -> str:
        words = line.split()
        with self.lock:
            match words:
                case ["I2C", address, data, length]:
                    return self._i2c(int(address), _hex(data), int(length))
                case ["SPI", _, data]:
                    return "OK:" + bytes(b ^ 0xFF for b in _hex(data)).hex()
                case ["UART", "CFG", baudrate, *rest]:
                    if int(baudrate) <= 0:
                        return "ERR:invalid baudrate"
                    self.uart_config = (baudrate, *rest)
                    return "OK:"
                case ["UART", "W", data]:
                    self.uart_rx += _hex(data)  # loopback
                    return "OK:"
                case ["UART", "R"]:
                    data, self.uart_rx = bytes(self.uart_rx), bytearray()
                    return "OK:" + data.hex()
        return f"ERR:unknown command {line!r}"

    def _i2c(self, address: int, data: bytes, length: int) -> str:
        """A register device : the first byte written sets the register pointer"""
        if address == NACK_ADDRESS:
            return "ERR:nack"
        memory = self.memory.setdefault(address, bytearray(256))
        if data:
            pointer = data[0]
            memory[pointer : pointer + len(data) - 1] = data[1:]
            self.pointer[address] = pointer
        pointer = self.pointer.get(address, 0)
        return "OK:" + bytes(memory[pointer : pointer + length]).hex()


def _hex(text: str) -> bytes:
    return b"" if text == "-" else bytes.fromhex(text)


@pytest.fixture
def board_server():
    state = BoardState()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            for line in self.rfile:
                answer = state.handle(line.decode().strip())
                self.wfile.write((answer + "\n").encode())

    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    ).start()
    yield server.server_address[1], state
    server.shutdown()
    server.server_close()


# ┌──────────────┐
# │ Bridge driver │
# └──────────────┘


class FakeBoard(Driver, I2CBridge, SPIBridge, SerialBridge):
    """Driver of the fake board, written like any blocking driver"""

    def __init__(self, adapter: IP) -> None:
        super().__init__()
        self._protocol = Delimited(adapter)

    def open(self) -> None:
        self._protocol.open()

    def close(self) -> None:
        self._protocol.close()

    def test(self) -> bool:
        return True

    def _command(self, text: str) -> bytes:
        answer = self._protocol.query(text)
        if not answer.startswith("OK:"):
            raise RuntimeError(f"Board error : {answer}")
        return bytes.fromhex(answer[3:])

    def i2c_transfer(self, address: int, data: bytes, read_length: int) -> bytes:
        return self._command(f"I2C {address} {data.hex() or '-'} {read_length}")

    def spi_transfer(self, cs: int, data: bytes) -> bytes:
        return self._command(f"SPI {cs} {data.hex() or '-'}")

    def serial_configure(
        self, baudrate: int, bytesize: int, parity: str, stopbits: int
    ) -> None:
        self._command(f"UART CFG {baudrate} {bytesize} {parity} {stopbits}")

    def serial_write(self, data: bytes) -> None:
        self._command(f"UART W {data.hex()}")

    def serial_read(self, timeout: float) -> bytes:
        return self._command("UART R")


@pytest.fixture
def board(board_server):
    port, _ = board_server
    return FakeBoard(IP("127.0.0.1", port))


# ┌─────┐
# │ I2C │
# └─────┘


def test_i2c_write_then_read_register(board):
    i2c = I2C(board, address=0x48)
    i2c.write(b"\x10\xaa\xbb")
    assert i2c.transfer(b"\x10", read_length=2) == b"\xaa\xbb"
    assert i2c.transfer(read_length=1) == b"\xaa"
    assert i2c.transfer(b"\x10\xcc") == b""
    assert i2c.query(I2CTransfer(b"\x10", 1)) == b"\xcc"


def test_i2c_is_an_adapter(board):
    i2c = I2C(board, address=0x48)
    assert isinstance(i2c, Adapter)
    assert str(i2c) == "i2c:FakeBoard@0x48"
    events: list[AdapterEvent] = []
    i2c.register_event_callback(events.append)
    i2c.transfer(b"\x00", read_length=1)
    kinds = {type(e) for e in events}
    assert AdapterWriteEvent in kinds and AdapterReadEvent in kinds
    i2c.close()
    assert not i2c.is_open


def test_i2c_devices_share_a_bridge(board):
    a = I2C(board, address=0x48)
    b = I2C(board, address=0x50)
    a.write(b"\x00\x01")
    b.write(b"\x00\x02")
    assert a.transfer(b"\x00", 1) == b"\x01"
    assert b.transfer(b"\x00", 1) == b"\x02"


def test_i2c_calls_from_several_threads_are_serialized(board):
    devices = [I2C(board, address=0x10 + i) for i in range(4)]
    errors: list[BaseException] = []

    def hammer(i2c: I2C) -> None:
        try:
            for value in range(20):
                i2c.write(bytes([0x00, value]))
                assert i2c.transfer(b"\x00", 1) == bytes([value])
        except BaseException as e:  # pylint: disable=broad-exception-caught
            errors.append(e)

    threads = [threading.Thread(target=hammer, args=(d,)) for d in devices]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


def test_i2c_bridge_error_reaches_the_caller_and_keeps_the_adapter_open(board):
    i2c = I2C(board, address=NACK_ADDRESS)
    with pytest.raises(RuntimeError, match="nack"):
        i2c.write(b"\x00")  # a plain write reports its NACK too
    with pytest.raises(RuntimeError, match="nack"):
        i2c.transfer(read_length=1)
    assert i2c.is_open


def test_i2c_rejects_wrong_length_and_address(board):
    class ShortBoard(FakeBoard):
        def i2c_transfer(self, address, data, read_length):
            return b""

    with pytest.raises(AdapterReadError):
        I2C(ShortBoard(board._protocol.adapter), 0x48).transfer(read_length=2)
    with pytest.raises(ValueError):
        I2C(board, address=0x80)
    with pytest.raises(ValueError):
        I2CTransfer(b"", -1)


def test_async_i2c(board):
    async def main() -> bytes:
        i2c = AsyncI2C(board, address=0x48)
        await i2c.write(b"\x20\x5a")
        return await i2c.transfer(b"\x20", read_length=1)

    assert asyncio.run(main()) == b"\x5a"


def test_i2c_descriptor():
    d = I2CDescriptor.from_string("i2c:/dev/i2c-1@0x48")
    assert (d.bus, d.address) == ("/dev/i2c-1", 0x48)
    assert str(d) == "i2c:/dev/i2c-1@0x48"


# ┌─────┐
# │ SPI │
# └─────┘


def test_spi_transfer(board):
    spi = SPI(board, cs=1)
    assert spi.transfer(b"\x00\x0f") == b"\xff\xf0"
    assert spi.query(b"\xff") == b"\x00"
    assert str(spi) == "spi:FakeBoard.1"


def test_spi_settings_belong_to_a_bridge_driver(board):
    with pytest.raises(ValueError, match="driver"):
        SPI(board, cs=1, mode=3)


def test_spi_write_keeps_what_was_received(board):
    """Full duplex : the bytes received during a plain write are a frame too"""
    spi = SPI(board)
    spi.write(b"\x0f")
    assert spi.read() == b"\xf0"


def test_async_spi(board):
    async def main() -> bytes:
        return await AsyncSPI(board).transfer(b"\x01")

    assert asyncio.run(main()) == b"\xfe"


# ┌────────────┐
# │ SerialPort │
# └────────────┘


def test_serial_loopback(board, board_server):
    _, state = board_server
    port = SerialPort(board, 115200)
    port.write(b"hello")
    assert port.read() == b"hello"
    assert state.uart_config == ("115200", "8", "N", "1")


def test_protocol_over_bridged_serial(board):
    """Delimited -> SerialPort -> FakeBoard -> Delimited -> IP"""
    protocol = Delimited(SerialPort(board, 9600))
    assert protocol.query("PING") == "PING"


def test_serial_and_i2c_on_the_same_bridge(board):
    port = SerialPort(board, 9600, stop_conditions=Termination(b"\n"))
    i2c = I2C(board, address=0x48)
    port.write(b"abc\n")
    i2c.write(b"\x00\x42")
    assert port.read() == b"abc\n"
    assert i2c.transfer(b"\x00", 1) == b"\x42"


def test_serial_configuration_failure(board):
    port = SerialPort(board, 0)  # the board refuses a zero baudrate
    with pytest.raises(AdapterWriteError, match="configuration failed"):
        port.write(b"x")
    port.open()
    with pytest.raises(AdapterOpenError, match="configuration failed"):
        port.read(timeout=1)


def test_serial_write_completes_once_the_bridge_sent_it(board):
    sent: list[bytes] = []

    class SlowBoard(FakeBoard):
        def serial_write(self, data):
            time.sleep(0.2)
            sent.append(data)

    port = SerialPort(SlowBoard(board._protocol.adapter), 9600)
    port.write(b"slow")
    assert sent == [b"slow"]


# ┌───────────────┐
# │ Bridge thread │
# └───────────────┘


def test_bridge_method_can_call_run_from_the_bridge_thread(board):
    """A bridge method waiting on run() from its own thread must not deadlock"""
    future = board.run(lambda: board.run(lambda: 42).result())
    assert future.result(timeout=2) == 42


def test_bridge_thread_stops_when_bridge_is_collected(board_server):
    port, _ = board_server
    board = FakeBoard(IP("127.0.0.1", port))
    I2C(board, 0x48).write(b"\x00")
    thread = board._worker().thread
    assert thread.is_alive()

    del board
    gc.collect()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_close_bridge_stops_the_thread_and_a_call_restarts_it(board):
    i2c = I2C(board, 0x48)
    i2c.write(b"\x00\x07")
    thread = board._worker().thread
    board.close_bridge()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert i2c.transfer(b"\x00", 1) == b"\x07"


# ┌──────────────┐
# │ Bridge names │
# └──────────────┘


class _NamedBoard(I2CBridge):
    def __init__(self, value: int = 0) -> None:
        self.value = value

    def i2c_transfer(self, address: int, data: bytes, read_length: int) -> bytes:
        return bytes(read_length)


def test_bridge_default_names_are_unique():
    gc.collect()  # No _NamedBoard of another test left
    first, second = _NamedBoard(), _NamedBoard()
    assert str(I2C(first, 0x10)) == "i2c:_NamedBoard@0x10"
    assert str(I2C(second, 0x10)) == "i2c:_NamedBoard#2@0x10"
    # A name is kept once given
    assert str(first) == "_NamedBoard"


def test_bridge_name_keyword():
    """Every bridge takes name, without its author declaring it"""
    left = _NamedBoard(3, name="left")
    assert left.value == 3
    assert str(I2C(left, 0x48)) == "i2c:left@0x48"
    assert "name" in inspect.signature(_NamedBoard.__init__).parameters
    # A default name doesn't repeat a chosen one
    other = _NamedBoard()
    other_named = _NamedBoard(name="_NamedBoard")
    assert str(other_named) == "_NamedBoard"
    assert str(other) != "_NamedBoard"


def test_bridge_keeps_its_own_name_parameter():
    class Board(I2CBridge):
        def __init__(self, name: str) -> None:
            self.name = name

        def i2c_transfer(self, address: int, data: bytes, read_length: int) -> bytes:
            return b""

    board = Board("not the bridge name")
    assert board.name == "not the bridge name"
    assert str(board) == "Board"


# ┌───────┐
# │ Order │
# └───────┘


class _EchoBoard(I2CBridge):
    """Answers at once, so that the answer races the end of the write"""

    def i2c_transfer(self, address: int, data: bytes, read_length: int) -> bytes:
        return bytes(data[:read_length])


def test_write_comes_before_its_answer(monkeypatch):
    """In the events and in the trace, a write is finished before its answer is read"""
    traced: list[str] = []
    monkeypatch.setattr(
        "syndesi.adapters.engine.tracehub._emit_event",
        lambda event: traced.append(type(event).__name__),
    )
    i2c = I2C(_EchoBoard(), 0x10)
    events: list[str] = []
    i2c.register_event_callback(lambda event: events.append(type(event).__name__))
    for _ in range(200):
        events.clear()
        traced.clear()
        assert i2c.transfer(b"\x01\x02", read_length=2) == b"\x01\x02"
        assert events.index("AdapterWriteEvent") < events.index("AdapterFragmentEvent")
        assert traced.index("WriteEvent") < traced.index("FragmentEvent")
    i2c.close()
