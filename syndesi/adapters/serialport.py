# File : serialport.py
# Author : Sébastien Deriaz
# License : GPL
"""
SerialPort adapter, talks to serial devices through the OS layer
(COMx, /dev/ttyUSBx or /dev/ttyACMx)
"""

from __future__ import annotations

import errno
import re
import sys
import time
from concurrent.futures import Future
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

import serial  # type: ignore #pylint: disable=import-error
from serial.serialutil import PortNotOpenError  # type: ignore #pylint: disable=import-error
from serial.tools.list_ports import comports  # type: ignore #pylint: disable=import-error

from ..bridges.bridge import SerialBridge
from ..errors import AdapterOpenError, AdapterReadError, AdapterWriteError
from ..tools.hints import busy_hint, permission_hint
from ..tools.others import DEFAULT, DefaultType
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
    Port and line settings of a serial port

    Written serial:port:baudrate (serial:/dev/ttyUSB0:115200, serial:COM4:9600), the
    baudrate is left out while it isn't known. port is the name of the bridge for a port
    provided by one. Only the port and the baudrate are part of the string
    """

    SCHEMES = ("serial",)
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
    def from_string(string: str) -> SerialPortDescriptor:
        _, target = SerialPortDescriptor.split_scheme(string)
        port, separator, baudrate = target.rpartition(":")
        if not separator or not baudrate.isdigit():
            port, baudrate = target, ""
        if not port:
            raise ValueError(
                f"Invalid descriptor : {string!r}, expected serial:port:baudrate"
            )
        return SerialPortDescriptor(port, int(baudrate) if baudrate else None)

    def __str__(self) -> str:
        baudrate = "" if self.baudrate is None else f":{self.baudrate}"
        return f"serial:{self.port}{baudrate}"

    def is_initialized(self) -> bool:
        return self.baudrate is not None

    def missing(self) -> str:
        return f"no baudrate given, for example SerialPort({self.port!r}, 115200)"


def _comports() -> list[Any]:
    """The pyserial ports worth showing, excluding ttyn and ttySn on Linux"""
    if sys.platform in ("linux", "linux2", "darwin"):
        return [p for p in comports() if not re.match(r"ttyS?(\d+)", p.name)]
    if sys.platform == "win32":
        return list(comports())
    raise RuntimeError(f"Invalid platform : {sys.platform}")


def list_ports() -> list[str]:
    """
    List the available serial ports, excluding ttyn and ttySn on Linux
    """
    return [p.device for p in _comports()]


def describe_ports() -> dict[str, str]:
    """
    The available serial ports and what is plugged in, as far as the system knows

    {'/dev/ttyACM0': 'Arduino Uno', 'COM3': 'USB-SERIAL CH340 (COM3)'}, an empty
    description if there is none
    """
    output = {}
    for port in _comports():
        description = port.description or ""
        if description in ("n/a", port.name, port.device):
            description = port.product or port.manufacturer or ""
        output[port.device] = description
    return output


def _open_error_message(port: str, error: serial.SerialException) -> str:
    """
    Explain why a port didn't open, and what to do about it

    pyserial gives the errno on Unix, and only the text of the Windows error on Windows
    """
    text = str(error)
    code = getattr(error, "errno", None)

    if code == errno.ENOENT or "No such file" in text or "FileNotFoundError" in text:
        ports = describe_ports()
        if ports:
            available = "Available ports : " + ", ".join(
                f"{device} ({description})" if description else device
                for device, description in ports.items()
            )
        else:
            available = "No serial port found, is the device plugged in ?"
        return f"Port '{port}' was not found. {available}"
    if code in (errno.EACCES, errno.EPERM) or "PermissionError" in text:
        hint = permission_hint(port)
        return f"Cannot open {port} : permission denied" + (f"\n{hint}" if hint else "")
    if code in (errno.EBUSY, errno.EAGAIN) or "exclusively lock" in text:
        return f"Cannot open {port} : port busy\n{busy_hint(port)}"
    return f"Cannot open {port} : {text}"


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
            raise AdapterOpenError(
                _open_error_message(self.descriptor.port, e)
            ) from None

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
            first = cast(bytes, port.read(1))
            if not first:
                return None
            rest = cast(bytes, port.read_all())
            output = first if rest is None else first + rest
            return output
        except (OSError, PortNotOpenError) as e:
            raise AdapterReadError(f"Cannot read from {self.descriptor} : {e}") from e


class BridgedSerialPortBackend(AdapterBackend[SerialPortDescriptor, bytes]):
    """
    Serial port provided by a bridge (custom board, serial server, ...)

    Runs on the reactor, which must never wait for the bridge : the bridge may itself
    wait for the reactor. So every call to the bridge is queued without waiting. Its
    queue runs them in order, the configuration always before the writes that follow
    the open

    The reads are a ThreadedReader calling serial_read() in a loop, through the bridge

    Parameters
    ----------
    bridge : SerialBridge
    descriptor : SerialPortDescriptor
    """

    def __init__(self, bridge: SerialBridge, descriptor: SerialPortDescriptor) -> None:
        super().__init__(descriptor)
        self._bridge = bridge
        self._reader: ThreadedReader[bytes] | None = None
        self._configured: Future[None] | None = None

    def selectable(self) -> HasFileno | None:
        return None if self._reader is None else self._reader.selectable()

    def open(self, timeout: float | None) -> None:
        del timeout  # the bridge has its own
        d = self.descriptor
        if d.baudrate is None:
            raise AdapterOpenError(f"Baudrate of {d} must be set before opening")
        self._configured = self._bridge.run(
            self._bridge.serial_configure, d.baudrate, d.bytesize, d.parity, d.stopbits
        )
        self._reader = ThreadedReader(
            self._read_once, name=f"syndesi-serial-{self._bridge}"
        )
        self._reader.start()

    def close(self) -> None:
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
        self._configured = None

    def write(self, data: bytes) -> Future[None]:
        return self._bridge.run(self._write_on_bridge, self._configured, data)

    def read(self, fragment_timestamp: float) -> Fragment[bytes]:
        if self._reader is None:
            raise AdapterReadError(f"{self.descriptor} is not open")
        return self._reader.read(fragment_timestamp)

    def reset_input_buffer(self) -> None:
        """Nothing to drop, the bridge holds no buffer of its own"""

    def flush_output(self) -> None:
        """Nothing to wait for, a write only completes once the bridge has sent it"""

    @property
    def default_timeout(self) -> TimeoutType:
        return 2.0

    def _write_on_bridge(self, configured: Future[None] | None, data: bytes) -> None:
        """Bridge thread : a port that couldn't be configured doesn't send anything"""
        if configured is None:
            raise AdapterWriteError(f"{self.descriptor} is not open")
        error = configured.exception()
        if error is not None:
            raise AdapterWriteError(
                f"{self.descriptor} : configuration failed ({error})"
            )
        self._bridge.serial_write(data)

    def _read_once(self) -> bytes | None:
        """Reader thread : one serial_read() through the bridge, paced when idle"""
        configured = self._configured
        if configured is not None:
            error = configured.exception()
            if error is not None:
                raise AdapterOpenError(
                    f"{self.descriptor} : configuration failed ({error})"
                )
        start = time.monotonic()
        period = self._bridge.SERIAL_POLL_PERIOD
        data = self._bridge.run(self._bridge.serial_read, period).result()
        if data:
            return data
        # Pause here, not on the bridge thread : the other users of the bridge go on
        time.sleep(max(0.0, period - (time.monotonic() - start)))
        return None


def _is_selectable(port: serial.Serial) -> bool:
    """
    True if the reactor can watch this port directly

    select() only takes sockets on Windows, and pyserial has no fileno() there either
    """
    if sys.platform == "win32":
        return False
    try:
        return cast(int, port.fileno()) >= 0
    except (OSError, ValueError, AttributeError, NotImplementedError):
        return False


def _make_backend(
    port: str | SerialBridge, descriptor: SerialPortDescriptor
) -> SerialPortBackend | BridgedSerialPortBackend:
    if isinstance(port, SerialBridge):
        return BridgedSerialPortBackend(port, descriptor)
    return SerialPortBackend(descriptor)


class SerialPort(Adapter[SerialPortDescriptor, bytes]):
    """
    Serial adapter, reads and writes bytes

    Parameters
    ----------
    port : str or SerialBridge
        Serial port (COMx, /dev/ttyUSBx or /dev/ttyACMx), or the bridge that provides
        it (custom board, serial server, ...)
    baudrate : int or None
        None lets a protocol set its default with set_default_baudrate
    timeout : float, None or DEFAULT
        Time to wait for the target to respond, 2 s by default
    stop_conditions : StopCondition, list of StopCondition or DEFAULT
        When a frame is complete, Continuation(0.1) by default
    alias : str
    bytesize, stopbits, parity, rts_cts, xon_xoff, dsr_dtr
        Line settings, see pyserial
    auto_open : bool
        Open on the first operation rather than at construction, so that a protocol
        can still set its default baudrate. Call open() to fail early
    """

    def __init__(
        self,
        port: str | SerialBridge,
        baudrate: int | None = None,
        *,
        timeout: TimeoutParameterType = DEFAULT,
        stop_conditions: StopCondition | list[StopCondition] | DefaultType = DEFAULT,
        alias: str = "",
        bytesize: int = 8,
        stopbits: int = 1,
        parity: str = Parity.NONE.value,
        rts_cts: bool = False,
        xon_xoff: bool = False,
        dsr_dtr: bool = False,
        auto_open: bool = True,
    ) -> None:
        self._backend = _make_backend(
            port,
            SerialPortDescriptor(
                port=str(port),
                baudrate=baudrate,
                bytesize=bytesize,
                stopbits=stopbits,
                parity=parity,
                rts_cts=rts_cts,
                dsr_dtr=dsr_dtr,
                xon_xoff=xon_xoff,
            ),
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
        port: str | SerialBridge,
        baudrate: int | None = None,
        *,
        timeout: TimeoutParameterType = DEFAULT,
        stop_conditions: StopCondition | list[StopCondition] | DefaultType = DEFAULT,
        alias: str = "",
        bytesize: int = 8,
        stopbits: int = 1,
        parity: str = Parity.NONE.value,
        rts_cts: bool = False,
        xon_xoff: bool = False,
        dsr_dtr: bool = False,
        auto_open: bool = True,
    ) -> None:
        self._backend = _make_backend(
            port,
            SerialPortDescriptor(
                port=str(port),
                baudrate=baudrate,
                bytesize=bytesize,
                stopbits=stopbits,
                parity=parity,
                rts_cts=rts_cts,
                dsr_dtr=dsr_dtr,
                xon_xoff=xon_xoff,
            ),
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
