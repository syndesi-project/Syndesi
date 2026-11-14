"""
Bridges : I2C, SPI and SerialPort provided by a driver

The board is faked by a TCP server speaking a line protocol, the bridge driver talks to
it through Delimited(IP(...)), the way a custom board on a serial port would be used
"""

import gc
import socketserver
import threading
import time

import pytest

from syndesi import (
    I2C,
    IP,
    SPI,
    Delimited,
    Driver,
    I2CBridge,
    SerialBridge,
    SerialPort,
    SPIBridge,
    Termination,
)
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
    assert i2c.write_read(b"\x10", 2) == b"\xaa\xbb"
    assert i2c.read(1) == b"\xaa"


def test_i2c_devices_share_a_bridge(board):
    a = I2C(board, address=0x48)
    b = I2C(board, address=0x50)
    a.write(b"\x00\x01")
    b.write(b"\x00\x02")
    assert a.write_read(b"\x00", 1) == b"\x01"
    assert b.write_read(b"\x00", 1) == b"\x02"


def test_i2c_calls_from_several_threads_are_serialized(board):
    devices = [I2C(board, address=0x10 + i) for i in range(4)]
    errors: list[BaseException] = []

    def hammer(i2c: I2C) -> None:
        try:
            for value in range(20):
                i2c.write(bytes([0x00, value]))
                assert i2c.write_read(b"\x00", 1) == bytes([value])
        except BaseException as e:  # pylint: disable=broad-exception-caught
            errors.append(e)

    threads = [threading.Thread(target=hammer, args=(d,)) for d in devices]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors


def test_i2c_bridge_error_reaches_the_caller(board):
    with pytest.raises(RuntimeError, match="nack"):
        I2C(board, address=NACK_ADDRESS).read(1)


def test_i2c_rejects_wrong_length_and_address(board):
    class ShortBoard(FakeBoard):
        def i2c_transfer(self, address, data, read_length):
            return b""

    with pytest.raises(AdapterReadError):
        I2C(ShortBoard(board._protocol.adapter), 0x48).read(2)
    with pytest.raises(ValueError):
        I2C(board, address=0x80)


# ┌─────┐
# │ SPI │
# └─────┘


def test_spi_transfer(board):
    spi = SPI(board, cs=1)
    assert spi.transfer(b"\x00\x0f") == b"\xff\xf0"


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
    assert i2c.write_read(b"\x00", 1) == b"\x42"


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
    assert i2c.write_read(b"\x00", 1) == b"\x07"
