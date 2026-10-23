"""
In-memory Modbus device for the tests

The device decodes the requests and encodes its answers with the SDU classes of
syndesi, the way a Modbus server would. It can be served over TCP, or over a pseudo
terminal with RTU or ASCII framing
"""

from __future__ import annotations

import os
import pty
import select
import socket
import struct
import threading
import tty
from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager

from syndesi.protocols.modbus import (
    REQUESTS,
    DiagnosticsCode,
    DiagnosticsRequestSDU,
    DiagnosticsResponseSDU,
    EncapsulatedInterfaceTransportRequestSDU,
    EncapsulatedInterfaceTransportResponseSDU,
    ExceptionResponseSDU,
    GetCommEventCounterRequestSDU,
    GetCommEventCounterResponseSDU,
    GetCommEventLogRequestSDU,
    GetCommEventLogResponseSDU,
    MaskWriteRegisterRequestSDU,
    MaskWriteRegisterResponseSDU,
    ModbusRequestSDU,
    ModbusResponseSDU,
    ReadCoilsRequestSDU,
    ReadCoilsResponseSDU,
    ReadDiscreteInputsRequestSDU,
    ReadDiscreteInputsResponseSDU,
    ReadExceptionStatusRequestSDU,
    ReadExceptionStatusResponseSDU,
    ReadFifoQueueRequestSDU,
    ReadFifoQueueResponseSDU,
    ReadFileRecordRequestSDU,
    ReadFileRecordResponseSDU,
    ReadHoldingRegistersRequestSDU,
    ReadHoldingRegistersResponseSDU,
    ReadInputRegistersRequestSDU,
    ReadInputRegistersResponseSDU,
    ReadWriteMultipleRegistersRequestSDU,
    ReadWriteMultipleRegistersResponseSDU,
    ReportServerIdRequestSDU,
    ReportServerIdResponseSDU,
    WriteFileRecordRequestSDU,
    WriteFileRecordResponseSDU,
    WriteMultipleCoilsRequestSDU,
    WriteMultipleCoilsResponseSDU,
    WriteMultipleRegistersRequestSDU,
    WriteMultipleRegistersResponseSDU,
    WriteSingleCoilRequestSDU,
    WriteSingleCoilResponseSDU,
    WriteSingleRegisterRequestSDU,
    WriteSingleRegisterResponseSDU,
    _ascii_frame,
    modbus_crc,
)

SLAVE_ADDRESS = 12
RTU_SILENCE = 0.02  # end of a request on the RTU line, in seconds

# Values returned by the functions that only report something
EXCEPTION_STATUS = 0x55
COUNTER_VALUE = 7
COMM_EVENT_COUNTER = (0xFFFF, 3)
COMM_EVENT_LOG = (0x0000, 3, 5, b"\x20\x00")
SERVER_ID = (b"FAKE", True, b"\x01\x02")
FIFO = [0x01B8, 0x1284]

# Diagnostics answered with a counter, the others echo the request data
COUNTERS = {
    DiagnosticsCode.RETURN_DIAGNOSTIC_REGISTER,
    DiagnosticsCode.RETURN_BUS_MESSAGE_COUNT,
    DiagnosticsCode.RETURN_BUS_COMMUNICATION_ERROR_COUNT,
    DiagnosticsCode.RETURN_BUS_EXCEPTION_ERROR_COUNT,
    DiagnosticsCode.RETURN_SERVER_NO_RESPONSE_COUNT,
    DiagnosticsCode.RETURN_SERVER_NAK_COUNT,
    DiagnosticsCode.RETURN_SERVER_BUSY_COUNT,
    DiagnosticsCode.RETURN_BUS_CHARACTER_OVERRUN_COUNT,
}


class FakeDevice:
    """
    Modbus device that keeps its data in memory

    Coils and discrete inputs share the same memory, so do holding and input
    registers. Set ``exception`` to make the next answer an exception response
    """

    def __init__(self) -> None:
        self.bits: defaultdict[int, bool] = defaultdict(bool)
        self.registers: defaultdict[int, int] = defaultdict(int)
        self.files: dict[tuple[int, int], bytes] = {}
        self.exception: int | None = None
        self.requests: list[ModbusRequestSDU] = []

    def handle(self, request: ModbusRequestSDU) -> ModbusResponseSDU | None:
        """Answer a request, None when the request has no answer"""
        self.requests.append(request)
        if self.exception is not None:
            code, self.exception = self.exception, None
            return ExceptionResponseSDU(request.function_code, code)

        match request:
            case ReadCoilsRequestSDU(address, n):
                return ReadCoilsResponseSDU(self._read_bits(address, n))
            case ReadDiscreteInputsRequestSDU(address, n):
                return ReadDiscreteInputsResponseSDU(self._read_bits(address, n))
            case ReadHoldingRegistersRequestSDU(address, n):
                return ReadHoldingRegistersResponseSDU(self._read_registers(address, n))
            case ReadInputRegistersRequestSDU(address, n):
                return ReadInputRegistersResponseSDU(self._read_registers(address, n))
            case WriteSingleCoilRequestSDU(address, status):
                self.bits[address] = status
                return WriteSingleCoilResponseSDU(address, status)
            case WriteSingleRegisterRequestSDU(address, value):
                self.registers[address] = value
                return WriteSingleRegisterResponseSDU(address, value)
            case ReadExceptionStatusRequestSDU():
                return ReadExceptionStatusResponseSDU(EXCEPTION_STATUS)
            case DiagnosticsRequestSDU(DiagnosticsCode.FORCE_LISTEN_ONLY_MODE):
                return None
            case DiagnosticsRequestSDU(code) if code in COUNTERS:
                return DiagnosticsResponseSDU(code, struct.pack(">H", COUNTER_VALUE))
            case DiagnosticsRequestSDU(code, data):
                return DiagnosticsResponseSDU(code, data)
            case GetCommEventCounterRequestSDU():
                return GetCommEventCounterResponseSDU(*COMM_EVENT_COUNTER)
            case GetCommEventLogRequestSDU():
                return GetCommEventLogResponseSDU(*COMM_EVENT_LOG)
            case WriteMultipleCoilsRequestSDU(address, values):
                self._write_bits(address, values)
                return WriteMultipleCoilsResponseSDU(address, len(values))
            case WriteMultipleRegistersRequestSDU(address, values):
                self._write_registers(address, values)
                return WriteMultipleRegistersResponseSDU(address, len(values))
            case ReportServerIdRequestSDU():
                return ReportServerIdResponseSDU(*SERVER_ID)
            case ReadFileRecordRequestSDU(records):
                return ReadFileRecordResponseSDU(
                    [
                        self.files.get((file, record), bytes(2 * length))
                        for file, record, length in records
                    ]
                )
            case WriteFileRecordRequestSDU(records):
                for file, record, data in records:
                    self.files[(file, record)] = data
                return WriteFileRecordResponseSDU(records)
            case MaskWriteRegisterRequestSDU(address, and_mask, or_mask):
                value = self.registers[address]
                self.registers[address] = (value & and_mask) | (or_mask & ~and_mask)
                return MaskWriteRegisterResponseSDU(address, and_mask, or_mask)
            case ReadWriteMultipleRegistersRequestSDU(read_address, n, write_address, values):
                self._write_registers(write_address, values)
                return ReadWriteMultipleRegistersResponseSDU(self._read_registers(read_address, n))
            case ReadFifoQueueRequestSDU():
                return ReadFifoQueueResponseSDU(FIFO)
            case EncapsulatedInterfaceTransportRequestSDU(mei_type, mei_data):
                return EncapsulatedInterfaceTransportResponseSDU(mei_type, mei_data)
        raise NotImplementedError(request)

    def answer(self, sdu: bytes) -> bytes | None:
        """Parse a request SDU and return the answer SDU"""
        response = self.handle(REQUESTS[sdu[0]].parse_sdu(sdu))
        return None if response is None else response.make_sdu()

    def _read_bits(self, address: int, n: int) -> list[bool]:
        return [self.bits[address + i] for i in range(n)]

    def _write_bits(self, address: int, values: list[bool]) -> None:
        for i, value in enumerate(values):
            self.bits[address + i] = value

    def _read_registers(self, address: int, n: int) -> list[int]:
        return [self.registers[address + i] for i in range(n)]

    def _write_registers(self, address: int, values: list[int]) -> None:
        for i, value in enumerate(values):
            self.registers[address + i] = value


# ┌─────────┐
# │ Servers │
# └─────────┘


@contextmanager
def serve_tcp(device: FakeDevice) -> Iterator[tuple[str, int]]:
    """Serve the device over Modbus TCP, yield the (host, port) to connect to"""
    server = socket.create_server(("localhost", 0))

    def run() -> None:
        while True:
            try:
                connection, _ = server.accept()
            except OSError:
                return  # server closed
            with connection:
                _serve_tcp_connection(device, connection)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield server.getsockname()
    finally:
        server.close()


def _serve_tcp_connection(device: FakeDevice, connection: socket.socket) -> None:
    stream = connection.makefile("rb")
    while header := stream.read(7):
        transaction_id, protocol_id, length, unit_id = struct.unpack(">HHHB", header)
        answer = device.answer(stream.read(length - 1))
        if answer is not None:
            connection.sendall(
                struct.pack(">HHHB", transaction_id, protocol_id, len(answer) + 1, unit_id) + answer
            )


@contextmanager
def serve_serial(device: FakeDevice, serial_type: str) -> Iterator[str]:
    """Serve the device over a pseudo terminal (RTU or ASCII), yield its path"""
    master, slave = pty.openpty()
    tty.setraw(slave)
    stop_read, stop_write = os.pipe()
    read_frame, unframe, frame = SERIAL_FRAMINGS[serial_type]

    def run() -> None:
        while (data := read_frame(master, stop_read)) is not None:
            address, sdu = unframe(data)
            answer = device.answer(sdu)
            if answer is not None:
                os.write(master, frame(address, answer))

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    try:
        yield os.ttyname(slave)
    finally:
        os.write(stop_write, b"x")
        thread.join(timeout=2)
        for fd in (master, slave, stop_read, stop_write):
            os.close(fd)


def _read_rtu_frame(fd: int, stop: int) -> bytes | None:
    """An RTU frame ends on a silence"""
    ready, _, _ = select.select([fd, stop], [], [])
    if stop in ready:
        return None
    data = b""
    while fd in ready:
        data += os.read(fd, 256)
        ready, _, _ = select.select([fd], [], [], RTU_SILENCE)
    return data


def _read_ascii_frame(fd: int, stop: int) -> bytes | None:
    """An ASCII frame ends with CRLF"""
    data = b""
    while not data.endswith(b"\r\n"):
        ready, _, _ = select.select([fd, stop], [], [])
        if stop in ready:
            return None
        data += os.read(fd, 256)
    return data


def _unframe_rtu(data: bytes) -> tuple[int, bytes]:
    assert struct.unpack("<H", data[-2:])[0] == modbus_crc(data[:-2])
    return data[0], data[1:-2]


def frame_rtu(address: int, sdu: bytes) -> bytes:
    frame = bytes([address]) + sdu
    return frame + struct.pack("<H", modbus_crc(frame))


def _unframe_ascii(data: bytes) -> tuple[int, bytes]:
    body = bytes.fromhex(data[1:-2].decode("ascii"))
    return body[0], body[1:-1]


# Read a request frame, extract (address, sdu) from it, frame an answer
SERIAL_FRAMINGS = {
    "rtu": (_read_rtu_frame, _unframe_rtu, frame_rtu),
    "ascii": (_read_ascii_frame, _unframe_ascii, _ascii_frame),
}


@contextmanager
def virtual_serial_pair():
    """Two pseudo terminals linked together, like a null-modem cable. Yields their paths"""
    m1, s1 = pty.openpty()
    m2, s2 = pty.openpty()
    for fd in (s1, s2):
        tty.setraw(fd)  # no echo, no CR/LF translation
    paths = (os.ttyname(s1), os.ttyname(s2))

    peer = {m1: m2, m2: m1}
    stop_r, stop_w = os.pipe()

    def relay():
        while True:
            ready, _, _ = select.select([m1, m2, stop_r], [], [])
            if stop_r in ready:
                return
            for fd in ready:
                data = os.read(fd, 4096)
                while data:
                    n = os.write(peer[fd], data)
                    data = data[n:]

    thread = threading.Thread(target=relay, daemon=True)
    thread.start()
    try:
        yield paths
    finally:
        os.write(stop_w, b"x")
        thread.join(timeout=2)
        for fd in (m1, s1, m2, s2, stop_r, stop_w):
            os.close(fd)
