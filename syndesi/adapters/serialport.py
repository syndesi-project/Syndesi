# File : serialport.py
# Author : Sébastien Deriaz
# License : GPL
"""
SerialPort adapter, talks to serial devices through the OS layer
(COMx, /dev/ttyUSBx or /dev/ttyACMx)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from enum import StrEnum
from types import EllipsisType

import serial
from serial.serialutil import PortNotOpenError
from serial.tools.list_ports import comports

from ..tools.errors import AdapterOpenError, AdapterReadError, AdapterWriteError
from .adapter import Adapter, AsyncAdapter
from .engine import AdapterBackend, Descriptor
from .framer import BytesFramer
from .reader_thread import ThreadedReader
from .stop_conditions import Continuation, StopCondition
from .utils import Fragment, HasFileno, TimeoutParameterType, TimeoutType


class Parity(StrEnum):
    """
    SerialPort parity setting, copied from pyserial
    """

    NONE = "N"
    EVEN = "E"
    ODD = "O"
    MARK = "M"
    SPACE = "S"


# pylint: disable=too-many-instance-attributes
@dataclass
class SerialPortDescriptor(Descriptor):
    """
    SerialPort descriptor that holds location (COMx or /dev/ttyx) and baudrate
    """

    DETECTION_PATTERN = r"^(COM\d+|/dev[/\w\d]+):\d+$"
    port: str
    # baudrate can be None to allow for a protocol to set its default
    baudrate: int | None = None
    bytesize: int = 8
    stopbits: int = 1
    parity: str = Parity.NONE.value
    rts_cts: bool = False
    dsr_dtr: bool = False
    xon_xoff: bool = False

    @staticmethod
    def from_string(string: str) -> "SerialPortDescriptor":
        parts = string.split(":")
        port = parts[0]
        baudrate = int(parts[1])
        return SerialPortDescriptor(port, baudrate)

    def __str__(self) -> str:
        return f"{self.port}:{self.baudrate}"

    def is_initialized(self) -> bool:
        return self.baudrate is not None


def list_ports() -> list[str]:
    """
    List the available serial ports, excluding ttyn and ttySn on Linux
    """
    if sys.platform in ("linux", "linux2", "darwin"):
        return [p.device for p in comports() if not re.match(r"ttyS?(\d+)", p.name)]
    if sys.platform == "win32":
        return [p.device for p in comports()]
    raise RuntimeError(f"Invalid platform : {sys.platform}")


def default_stop_conditions() -> list[StopCondition]:
    """
    Stop-conditions of a new serial adapter

    A function, not a module level list : a stop-condition holds the state of the frame
    being assembled, so two adapters must never share the same instances
    """
    return [Continuation(continuation=0.1)]


class SerialPortBackend(AdapterBackend[SerialPortDescriptor, bytes]):
    """
    Talks to a serial port through pyserial

    On Linux and macOS the port has a usable fileno(), so the reactor watches it
    directly. On Windows it doesn't, and select() only accepts sockets there, so the
    reads go through a ThreadedReader

    Parameters
    ----------
    descriptor : SerialPortDescriptor
    """

    # How long a threaded read blocks before it checks whether it must stop
    THREAD_READ_TIMEOUT = 0.05

    def __init__(self, descriptor: SerialPortDescriptor) -> None:
        super().__init__(descriptor)
        self._port: serial.Serial | None = None
        self._reader: ThreadedReader[bytes] | None = None

    def selectable(self) -> HasFileno | None:
        if self._reader is not None:
            return self._reader.selectable()
        return self._port

    def open(self, timeout: float | None) -> None:
        del timeout  # opening a serial port is not a network operation
        baudrate = self.descriptor.baudrate
        if baudrate is None:
            raise AdapterOpenError(
                f"Baudrate of {self.descriptor} must be set before opening"
            )

        try:
            port = serial.Serial(
                port=self.descriptor.port,
                baudrate=baudrate,
                bytesize=self.descriptor.bytesize,
                parity=self.descriptor.parity,
                stopbits=self.descriptor.stopbits,
                rtscts=self.descriptor.rts_cts,
                xonxoff=self.descriptor.xon_xoff,
                dsrdtr=self.descriptor.dsr_dtr,
                timeout=self.THREAD_READ_TIMEOUT,
                exclusive=True,
            )
        except serial.SerialException as e:
            if "No such file" in str(e):
                raise AdapterOpenError(
                    f"Port '{self.descriptor.port}' was not found"
                ) from e
            raise AdapterOpenError(f"SerialPort open error : {e}") from None

        if not port.is_open:
            raise AdapterOpenError(f"Port '{self.descriptor.port}' did not open")

        self._port = port
        if not _is_selectable(port):
            self._reader = ThreadedReader(
                self._read_blocking, name=f"syndesi-serial-{self.descriptor.port}"
            )
            self._reader.start()

    def close(self) -> None:
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
        if self._port is not None:
            self._port.close()
            self._port = None

    def read(self, fragment_timestamp: float) -> Fragment[bytes]:
        if self._reader is not None:
            return self._reader.read(fragment_timestamp)

        if self._port is None:
            raise AdapterReadError(f"{self.descriptor} is not open")
        try:
            data = self._port.read_all()
        except (OSError, PortNotOpenError) as e:
            raise AdapterReadError(f"Cannot read from {self.descriptor} : {e}") from e

        if data is None or not data:
            raise AdapterReadError(f"{self.descriptor} reported data but had none")
        return Fragment(data, fragment_timestamp)

    def write(self, data: bytes) -> None:
        if self._port is None:
            raise AdapterWriteError(f"{self.descriptor} is not open")
        if self.descriptor.rts_cts:  # Experimental
            self._port.rts = True
        try:
            self._port.write(data)
        except (OSError, PortNotOpenError) as e:
            raise AdapterWriteError(f"Cannot write to {self.descriptor} : {e}") from e

    def reset_input_buffer(self) -> None:
        """
        Drop what the OS has buffered but not handed over yet

        Serial.flush() is not this : it waits for the write buffer to drain
        """
        if self._port is not None:
            self._port.reset_input_buffer()

    def flush_output(self) -> None:
        """Wait for the data still in the OS write buffer to be sent"""
        if self._port is not None:
            self._port.flush()

    @property
    def default_timeout(self) -> TimeoutType:
        return 2.0

    def _read_blocking(self) -> bytes | None:
        """
        One blocking read for the ThreadedReader

        Waits for a single byte with the port timeout, then takes whatever else already
        arrived, so a fragment stays a fragment instead of becoming one byte
        """
        port = self._port
        if port is None:
            return None
        try:
            first = port.read(1)
            if not first:
                return None
            rest = port.read_all()
            return first if rest is None else first + rest
        except (OSError, PortNotOpenError) as e:
            raise AdapterReadError(f"Cannot read from {self.descriptor} : {e}") from e


def _is_selectable(port: serial.Serial) -> bool:
    """
    True if the reactor can watch this port directly

    select() only takes sockets on Windows, and pyserial has no fileno() there either
    """
    if sys.platform == "win32":
        return False
    try:
        return port.fileno() >= 0
    except (OSError, ValueError, AttributeError, NotImplementedError):
        return False


class SerialPort(Adapter[SerialPortDescriptor, bytes]):
    """
    Serial adapter, reads and writes bytes

    Parameters
    ----------
    port : str
        Serial port (COMx, /dev/ttyUSBx or /dev/ttyACMx)
    baudrate : int or None
        None lets a protocol set its default with set_default_baudrate
    timeout : float, None or ...
        Time to wait for the target to respond, 2 s by default
    stop_conditions : StopCondition, list of StopCondition or ...
        When a frame is complete, Continuation(0.1) by default
    alias : str
    bytesize, stopbits, parity, rts_cts, xon_xoff, dsr_dtr
        Line settings, see pyserial
    auto_open : bool
        Open on construction, skipped while the baudrate is None
    """

    def __init__(
        self,
        port: str,
        baudrate: int | None = None,
        *,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        bytesize: int = 8,
        stopbits: int = 1,
        parity: str = Parity.NONE.value,
        rts_cts: bool = False,
        xon_xoff: bool = False,
        dsr_dtr: bool = False,
        auto_open: bool = True,
    ) -> None:
        self._backend = SerialPortBackend(
            SerialPortDescriptor(
                port=port,
                baudrate=baudrate,
                bytesize=bytesize,
                stopbits=stopbits,
                parity=parity,
                rts_cts=rts_cts,
                dsr_dtr=dsr_dtr,
                xon_xoff=xon_xoff,
            )
        )
        super().__init__(
            self._backend,
            BytesFramer(default_stop_conditions()),
            timeout,
            stop_conditions=stop_conditions,
            alias=alias,
            auto_open=auto_open,
        )

    @staticmethod
    def list_ports() -> list[str]:
        """List the available serial ports"""
        return list_ports()

    def set_default_baudrate(self, baudrate: int) -> None:
        """
        Set the baudrate, unless one was given. Reopens the port if it was already open
        """
        if self.descriptor.baudrate is not None:
            return
        self.descriptor.baudrate = baudrate
        if self.is_open:
            self.close()
        self.open()

    def clear_read_buffer(self) -> None:
        """Drop the OS input buffer, then the frames and the one being assembled"""
        self._backend.reset_input_buffer()
        super().clear_read_buffer()

    def flush(self) -> None:
        """Wait for the data still in the OS write buffer to be sent"""
        self._backend.flush_output()


class AsyncSerialPort(AsyncAdapter[SerialPortDescriptor, bytes]):
    """
    Async serial adapter, same parameters as SerialPort
    """

    def __init__(
        self,
        port: str,
        baudrate: int | None = None,
        *,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        bytesize: int = 8,
        stopbits: int = 1,
        parity: str = Parity.NONE.value,
        rts_cts: bool = False,
        xon_xoff: bool = False,
        dsr_dtr: bool = False,
        auto_open: bool = True,
    ) -> None:
        self._backend = SerialPortBackend(
            SerialPortDescriptor(
                port=port,
                baudrate=baudrate,
                bytesize=bytesize,
                stopbits=stopbits,
                parity=parity,
                rts_cts=rts_cts,
                dsr_dtr=dsr_dtr,
                xon_xoff=xon_xoff,
            )
        )
        super().__init__(
            self._backend,
            BytesFramer(default_stop_conditions()),
            timeout,
            stop_conditions=stop_conditions,
            alias=alias,
            auto_open=auto_open,
        )

    @staticmethod
    def list_ports() -> list[str]:
        """List the available serial ports"""
        return list_ports()

    async def set_default_baudrate(self, baudrate: int) -> None:
        """
        Set the baudrate, unless one was given. Reopens the port if it was already open
        """
        if self.descriptor.baudrate is not None:
            return
        self.descriptor.baudrate = baudrate
        if self.is_open:
            await self.close()
        await self.open()

    async def clear_read_buffer(self) -> None:
        """Drop the OS input buffer, then the frames and the one being assembled"""
        self._backend.reset_input_buffer()
        await super().clear_read_buffer()

    def flush(self) -> None:
        """Wait for the data still in the OS write buffer to be sent"""
        self._backend.flush_output()
