# File : backend.py
# Author : Sébastien Deriaz
# License : GPL
"""
Modbus framing : TCP over IP, RTU and ASCII over a serial port

PDU (Protocol Data Unit) format

Modbus TCP
┌────────────────┬─────────────┬────────┬─────────┬───────┐
│ Transaction ID │ Protocol ID │ Length │ Unit ID │ Data  │
└────────────────┴─────────────┴────────┴─────────┴───────┘
      2 bytes        2 bytes     2 bytes   1 byte  N bytes


Modbus RTU
┌───────────────┬────────┬────────┐
│ Slave address │  Data  │  CRC   │
└───────────────┴────────┴────────┘
     1 byte       N bytes  2 bytes

Modbus ASCII
┌────────┬───────────────┬────────┬───────┬─────────┐
│ HEADER │ Slave address │  Data  │  CRC  │ TRAILER │
└────────┴───────────────┴────────┴───────┴─────────┘
  1 byte      1 byte       N bytes 2 bytes   1 byte


The PDU is built and parsed by ModbusBackend, each data block (SDU) is constructed
by its corresponding ModbusRequestSDU class. SDUs are parsed by ModbusResponseSDU
classes

Framing : the MBAP header carries the length of what follows, so the backend takes
FragmentSC() and cuts the frames itself from the raw fragments. Stop-conditions
cannot do it, a single read can bring header and body together
"""

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, ClassVar

from ...adapters.framer import AdapterReadFrame
from ...adapters.stop_conditions import (
    Continuation,
    FragmentSC,
    StopCondition,
    Termination,
)
from ...adapters.utils import TimeoutParameterType, TimeoutType
from ...tools.errors import ProtocolError, ProtocolReadError
from ...tools.others import DEFAULT
from ..protocol import (
    BackendOutput,
    ProtocolBackend,
    ProtocolEvent,
)
from .common import (
    ENDIAN,
    ExceptionCode,
    ModbusAddressError,
)
from .sdu import (
    REQUESTS,
    RESPONSES,
    ExceptionResponseSDU,
    ModbusRequestSDU,
    ModbusResponseSDU,
    ModbusSDU,
    SerialLineOnlySDU,
)

_ASCII_HEADER = b":"
_PROTOCO_ID = 0
_UNIT_ID = 0
_ASCII_TRAILER = b"\r\n"


class ModbusSerialType(StrEnum):
    """
    Modbus type over serial

    - RTU : Modbus over serial
    - ASCII : Modbus using text based encoding
    """

    RTU = "RTU"
    ASCII = "ASCII"


def modbus_crc(_bytes: bytes) -> int:
    """
    CRC-16/MODBUS of the given buffer

    Reflected polynomial 0xA001, initial value 0xFFFF. On the wire the result travels
    low byte first, which is why it is packed little endian and not with ENDIAN
    """
    crc = 0xFFFF
    for byte in _bytes:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def modbus_lrc(_bytes: bytes) -> int:
    """
    LRC of the given buffer, the check used by Modbus ASCII

    Two's complement of the sum of every byte, truncated to 8 bits
    """
    return (-sum(_bytes)) & 0xFF


def _ascii_frame(slave_address: int, sdu: bytes) -> bytes:
    """``:`` then the frame and its LRC as uppercase hex, then CRLF"""
    frame = struct.pack(ENDIAN + "B", slave_address) + sdu
    body = frame + struct.pack(ENDIAN + "B", modbus_lrc(frame))
    return _ASCII_HEADER + body.hex().upper().encode("ascii") + _ASCII_TRAILER


MBAP_LENGTH = 6  # transaction id, protocol id, length : the fixed part of the header
BROADCAST_ADDRESS = 0


@dataclass
class ModbusExceptionEvent(ProtocolEvent):
    """
    An exception response went through the backend

    Received by a client, or made by a server backend for a request it couldn't accept
    """

    response: ExceptionResponseSDU


class ModbusBackend(ProtocolBackend[bytes, ModbusSDU]):
    """
    Builds and parses the Modbus frames around the SDUs, as a client or as a server

    A client writes requests and reads responses, a server reads requests and writes
    responses. The framing is the same both ways, only what is inside changes

    The backend keeps state :

    * a client response cannot be parsed on its own. Reading 10 coils and reading 3
      gives the same bytes on the wire, only the request says how to read them, so the
      SDU that was written is kept and used to parse what comes back
    * a server response is framed like the request it answers (transaction id in TCP,
      broadcast or not on a serial line), so that is kept until the response is written
    * the TCP frame length lives in the header. FragmentSC() hands the raw fragments
      over and the assembly happens here, which is also what makes coalesced frames
      work

    Parameters
    ----------
    server : bool
        False for a client (default), True for a server
    """

    # Whether the serial line only function codes can be used
    serial_line: ClassVar[bool]

    def __init__(self, *, server: bool = False) -> None:
        self._server = server
        self._last_sdu: ModbusRequestSDU | None = None
        self._buffer = b""

    # ┌──────────┐
    # │ Encoding │
    # └──────────┘

    def encode(self, payload: ModbusSDU) -> list[bytes]:
        if self._server:
            if not isinstance(payload, ModbusResponseSDU):
                raise RuntimeError("A Modbus server can only encode ModbusResponseSDU")
            return self._encode_response(payload.make_sdu())

        if not isinstance(payload, ModbusRequestSDU):
            raise RuntimeError("Can only encode ModbusRequestSDU")
        if isinstance(payload, SerialLineOnlySDU) and not self.serial_line:
            raise ProtocolError("This function cannot be used with Modbus TCP")
        # Kept for parse_sdu, the answer alone doesn't say how to read itself
        self._last_sdu = payload
        return [self._encode_request(payload.make_sdu())]

    @abstractmethod
    def _encode_request(self, sdu: bytes) -> bytes:
        """Frame a request SDU"""

    @abstractmethod
    def _encode_response(self, sdu: bytes) -> list[bytes]:
        """Frame a response SDU like the request it answers, nothing if it has no answer"""

    # ┌──────────┐
    # │ Parsing  │
    # └──────────┘

    def _parse_sdu(self, sdu: bytes) -> ModbusSDU:
        """Parse a received SDU : a response for a client, a request for a server"""
        if self._server:
            return self._parse_request(sdu)
        return self._parse_response(sdu)

    def _parse_response(self, sdu: bytes) -> ModbusResponseSDU[Any]:
        """
        Parse the SDU of a response with the request that was last written

        An exception response is returned as an ExceptionResponseSDU, not raised, it is
        up to the caller to decide what to do with it
        """
        request = self._last_sdu
        if request is None:
            raise ProtocolReadError("Cannot read without a prior write")
        if sdu == b"":
            raise ProtocolReadError("Empty Modbus response")

        try:
            if ExceptionResponseSDU.is_exception(sdu):
                return ExceptionResponseSDU.parse_sdu(sdu, request)
            if sdu[0] != request.function_code:
                raise ProtocolReadError(
                    f"Function code mismatch : got {sdu[0]}, "
                    f"expected {request.function_code}"
                )
            return RESPONSES[request.function_code].parse_sdu(sdu, request)
        except (struct.error, IndexError) as e:
            raise ProtocolReadError(f"Malformed Modbus response : {sdu!r}") from e

    def _parse_request(self, sdu: bytes) -> ModbusSDU:
        """
        Parse the SDU of a request

        A request the server cannot accept is returned as the ExceptionResponseSDU
        that answers it
        """
        if sdu == b"":
            raise ProtocolReadError("Empty Modbus request")

        request_type = REQUESTS.get(sdu[0])
        if request_type is None or (
            issubclass(request_type, SerialLineOnlySDU) and not self.serial_line
        ):
            return ExceptionResponseSDU(sdu[0], ExceptionCode.ILLEGAL_FUNCTION)
        try:
            return request_type.parse_sdu(sdu)
        except ModbusAddressError:
            return ExceptionResponseSDU(sdu[0], ExceptionCode.ILLEGAL_DATA_ADDRESS)
        except (ValueError, struct.error, IndexError):
            return ExceptionResponseSDU(sdu[0], ExceptionCode.ILLEGAL_DATA_VALUE)

    # ┌───────────┐
    # │ Assembly  │
    # └───────────┘

    @staticmethod
    def _output(payloads: list[ModbusSDU]) -> BackendOutput[bytes, ModbusSDU]:
        """The payloads, with an event for each exception response among them"""
        return BackendOutput(
            payloads=payloads,
            events=[
                ModbusExceptionEvent(payload)
                for payload in payloads
                if isinstance(payload, ExceptionResponseSDU)
            ],
        )

    @abstractmethod
    def push(
        self, frame: AdapterReadFrame[bytes]
    ) -> BackendOutput[bytes, ModbusSDU]: ...

    @property
    def in_progress(self) -> bool:
        return len(self._buffer) > 0

    def reset(self) -> None:
        self._buffer = b""

    @property
    def default_timeout(self) -> TimeoutType:
        # A server waits for requests for as long as it takes
        return None if self._server else 1.0

    @property
    def adapter_default_timeout(self) -> TimeoutParameterType:
        return None if self._server else DEFAULT


class ModbusTCPBackend(ModbusBackend):
    """Modbus TCP, frames carry an MBAP header"""

    serial_line = False

    def __init__(self, *, server: bool = False) -> None:
        super().__init__(server=server)
        self._transaction_id = 0
        # (transaction id, unit id) of the requests not answered yet, in order
        self._requests: deque[tuple[int, int]] = deque()

    @property
    def stop_conditions(self) -> list[StopCondition]:
        # The MBAP header carries the length, the backend cuts the frames itself
        return [FragmentSC()]

    def push(self, frame: AdapterReadFrame[bytes]) -> BackendOutput[bytes, ModbusSDU]:
        self._buffer += frame.data
        payloads: list[ModbusSDU] = []

        while len(self._buffer) >= MBAP_LENGTH:
            (length,) = struct.unpack(ENDIAN + "H", self._buffer[4:MBAP_LENGTH])
            total = MBAP_LENGTH + length
            if len(self._buffer) < total:
                break  # the body hasn't arrived yet
            payloads.append(self._parse(self._buffer[:total]))
            self._buffer = self._buffer[total:]

        return self._output(payloads)

    def _parse(self, pdu: bytes) -> ModbusSDU:
        """Check the MBAP header, return the SDU"""
        if len(pdu) < MBAP_LENGTH + 1:  # header + unit id
            raise ProtocolReadError(f"Modbus TCP frame is too short : {pdu!r}")
        transaction_id, protocol_id, _, unit_id = struct.unpack(
            ENDIAN + "HHHB", pdu[: MBAP_LENGTH + 1]
        )
        if protocol_id != _PROTOCO_ID:
            raise ProtocolReadError(f"Invalid Modbus TCP protocol id : {protocol_id}")
        if self._server:
            self._requests.append((transaction_id, unit_id))

        return self._parse_sdu(pdu[MBAP_LENGTH + 1 :])

    def _encode_request(self, sdu: bytes) -> bytes:
        output = _mbap_frame(self._transaction_id, _UNIT_ID, sdu)
        self._transaction_id = (self._transaction_id + 1) % 0x10000
        return output

    def _encode_response(self, sdu: bytes) -> list[bytes]:
        if not self._requests:
            raise ProtocolError("There is no request to answer")
        transaction_id, unit_id = self._requests.popleft()
        return [_mbap_frame(transaction_id, unit_id, sdu)]


def _mbap_frame(transaction_id: int, unit_id: int, sdu: bytes) -> bytes:
    length = len(sdu) + 1  # unit_id is included
    return (
        struct.pack(ENDIAN + "HHHB", transaction_id, _PROTOCO_ID, length, unit_id) + sdu
    )


class ModbusSerialBackend(ModbusBackend, ABC):
    """
    Modbus over a serial line, RTU and ASCII only differ by their framing

    A client only accepts answers from its slave. A server only reads the requests
    addressed to it and the broadcasts, which it doesn't answer
    """

    serial_line = True

    def __init__(self, slave_address: int, *, server: bool = False) -> None:
        super().__init__(server=server)
        self._slave_address = slave_address
        self._request_address = slave_address

    def push(self, frame: AdapterReadFrame[bytes]) -> BackendOutput[bytes, ModbusSDU]:
        # RTU and ASCII are framed by the adapter (silence, trailer), one adapter frame
        # is one Modbus frame
        address, sdu = self._unframe(frame.data)

        if self._server:
            if address not in (self._slave_address, BROADCAST_ADDRESS):
                return BackendOutput()  # for another slave
            self._request_address = address
        elif address != self._slave_address:
            raise ProtocolReadError(
                f"Modbus answer came from slave {address}, "
                f"expected {self._slave_address}"
            )

        return self._output([self._parse_sdu(sdu)])

    def _encode_request(self, sdu: bytes) -> bytes:
        return self._frame(self._slave_address, sdu)

    def _encode_response(self, sdu: bytes) -> list[bytes]:
        if self._request_address == BROADCAST_ADDRESS:
            return []  # a broadcast is never answered
        return [self._frame(self._slave_address, sdu)]

    @abstractmethod
    def _unframe(self, pdu: bytes) -> tuple[int, bytes]:
        """Check a frame, return its (address, SDU)"""

    @abstractmethod
    def _frame(self, address: int, sdu: bytes) -> bytes:
        """Frame an SDU for the given address"""


class ModbusASCIIBackend(ModbusSerialBackend):
    """Modbus ASCII, frames are hexadecimal text with an LRC"""

    @property
    def stop_conditions(self) -> list[StopCondition]:
        # Every ASCII frame ends with CRLF
        return [Termination(_ASCII_TRAILER)]

    def _unframe(self, pdu: bytes) -> tuple[int, bytes]:
        """Decode the hex and check the LRC"""
        if not pdu.startswith(_ASCII_HEADER) or not pdu.endswith(_ASCII_TRAILER):
            raise ProtocolReadError(f"Malformed Modbus ASCII frame : {pdu!r}")

        hex_body = pdu[len(_ASCII_HEADER) : -len(_ASCII_TRAILER)]
        try:
            body = bytes.fromhex(hex_body.decode("ascii"))
        except (ValueError, UnicodeDecodeError) as e:
            raise ProtocolReadError(
                f"Modbus ASCII frame isn't hex : {hex_body!r}"
            ) from e

        if len(body) < 3:  # address + at least a function code + LRC
            raise ProtocolReadError(f"Modbus ASCII frame is too short : {pdu!r}")

        received = body[-1]
        expected = modbus_lrc(body[:-1])
        if received != expected:
            raise ProtocolReadError(
                f"Modbus ASCII LRC mismatch : got {received:02X}, expected {expected:02X}"
            )

        return body[0], body[1:-1]

    def _frame(self, address: int, sdu: bytes) -> bytes:
        return _ascii_frame(address, sdu)


class ModbusRTUBackend(ModbusSerialBackend):
    """Modbus RTU, binary frames with a CRC, separated by silences"""

    def __init__(
        self, slave_address: int, baudrate: int, *, server: bool = False
    ) -> None:
        super().__init__(slave_address, server=server)

        # Silence that ends an RTU frame, in seconds
        # 3.5 character (11 bits) times below 19200, fixed 1.75ms above
        self._silence = 1.75e-3 if baudrate > 19200 else (3.5 * 11 / baudrate)

    @property
    def stop_conditions(self) -> list[StopCondition]:
        # An RTU frame ends on a silence on the line
        return [Continuation(self._silence)]

    def _unframe(self, pdu: bytes) -> tuple[int, bytes]:
        """Check the CRC"""
        if len(pdu) < 4:  # address + at least a function code + CRC
            raise ProtocolReadError(f"Modbus RTU frame is too short : {pdu!r}")

        (received,) = struct.unpack("<H", pdu[-2:])
        expected = modbus_crc(pdu[:-2])
        if received != expected:
            raise ProtocolReadError(
                f"Modbus RTU CRC mismatch : got {received:04X}, expected {expected:04X}"
            )

        return pdu[0], pdu[1:-2]

    def _frame(self, address: int, sdu: bytes) -> bytes:
        frame = struct.pack(ENDIAN + "B", address) + sdu
        return frame + struct.pack("<H", modbus_crc(frame))


def _serial_backend(
    serial_type: str,
    slave_address: int | None,
    baudrate: int | None,
    *,
    server: bool = False,
) -> ModbusBackend:
    """Check the serial parameters and pick the RTU or ASCII backend"""
    if slave_address is None:
        raise ValueError("slave_address must be set for Modbus RTU and ASCII")
    if not 1 <= slave_address <= 247:
        raise ValueError(f"Invalid slave address : {slave_address}, expected 1 to 247")
    if baudrate is None:
        raise ValueError("Baudrate hasn't been defined")
    try:
        _type = ModbusSerialType(serial_type.upper())
    except ValueError as e:
        raise ValueError(f"Invalid modbus serial type : {serial_type}") from e
    if _type == ModbusSerialType.ASCII:
        return ModbusASCIIBackend(slave_address, server=server)
    return ModbusRTUBackend(slave_address, baudrate, server=server)
