# File : serialport.py
# Author : Sébastien Deriaz
# License : GPL

"""
SerialPort module, allows communication with serial devices using
the OS layers (COMx, /dev/ttyUSBx or /dev/ttyACMx)

"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from types import EllipsisType

import serial
from serial.serialutil import PortNotOpenError

from syndesi.adapters.adapter_worker import AdapterEvent, HasFileno
from syndesi.component import Descriptor
from syndesi.tools.errors import AdapterOpenError, AdapterReadError
from syndesi.tools.types import NumberLike

from .adapter import BytesAdapter
from .stop_conditions import Continuation, Fragment, StopCondition
from .timeout import Timeout


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

    DETECTION_PATTERN = r"(COM\d+|/dev[/\w\d]+):\d+"
    port: str
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

    def set_default_baudrate(self, baudrate: int) -> bool:
        """
        Set the baudrate if it has not be defined before

        Parameters
        ----------
        baudrate : int
        """
        if self.baudrate is None:
            self.baudrate = baudrate
            return True

        return False

    def __str__(self) -> str:
        return f"{self.port}:{self.baudrate}"

    def is_initialized(self) -> bool:
        return self.baudrate is not None


class SerialPort(BytesAdapter):
    """
    Serial communication adapter

    Parameters
    ----------
    port : str
        Serial port (COMx or ttyACMx)
    baudrate : int
        Baudrate
    """

    _open_ports: set[str] = set()
    _open_ports_lock = threading.Lock()

    def __init__(
        self,
        port: str,
        baudrate: int | None = None,
        *,
        timeout: Timeout | NumberLike | None | EllipsisType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        bytesize: int = 8,
        stopbits: int = 1,
        parity: str = Parity.NONE.value,
        rts_cts: bool = False,
        xon_xoff: bool = False,
        dsr_dtr: bool = False,
        event_callback: Callable[[AdapterEvent], None] | None = None,
        auto_open: bool = True,
    ) -> None:
        """
        Instanciate new SerialPort adapter
        """
        self._port: serial.Serial | None = None
        descriptor = SerialPortDescriptor(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            stopbits=stopbits,
            parity=parity,
            rts_cts=rts_cts,
            dsr_dtr=dsr_dtr,
            xon_xoff=xon_xoff,
        )
        super().__init__(
            descriptor=descriptor,
            timeout=timeout,
            stop_conditions=stop_conditions,
            alias=alias,
            event_callback=event_callback,
            auto_open=auto_open,
        )
        self._descriptor: SerialPortDescriptor
        self._worker_descriptor: SerialPortDescriptor

        self._logger.info(
            f"Setting up SerialPort adapter {self._descriptor}, \
                timeout={timeout} and stop_conditions={self._stop_conditions}"
        )

        # self._bytesize = bytesize
        # self._stopbits = stopbits
        # self._parity = Parity(parity)
        # self._xonxoff = xon_xoff
        # self._dsrdtr = dsr_dtr

    def _default_timeout(self) -> Timeout:
        return Timeout(response=2, action="error")

    def _default_stop_conditions(self) -> list[StopCondition]:
        return [Continuation(0.1)]

    def _worker_open(self) -> None:
        super()._worker_open()
        self._worker_check_descriptor()

        if self._worker_descriptor.baudrate is None:
            raise AdapterOpenError(
                "Descriptor must be fully initialized to open the adapter"
            )

        if self._port is not None:
            self.close()

        port_name = self._worker_descriptor.port
        with self._open_ports_lock:
            if port_name in self._open_ports:
                raise AdapterOpenError(f"Port '{port_name}' is already in use")
            self._open_ports.add(port_name)

        try:
            self._port = serial.Serial(
                port=self._worker_descriptor.port,
                baudrate=self._worker_descriptor.baudrate,
                rtscts=self._worker_descriptor.rts_cts,
                bytesize=self._worker_descriptor.bytesize,
                parity=self._worker_descriptor.parity,
                stopbits=self._worker_descriptor.stopbits,
                xonxoff=self._worker_descriptor.xon_xoff,
                dsrdtr=self._worker_descriptor.dsr_dtr
            )
        except serial.SerialException as e:
            with self._open_ports_lock:
                self._open_ports.discard(port_name)
            if "No such file" in str(e):
                raise AdapterOpenError(
                    f"Port '{self._worker_descriptor.port}' was not found"
                ) from e
            raise AdapterOpenError("Unknown error") from e

        if self._port.isOpen():  # type: ignore
            self._logger.info(f"Adapter {self._worker_descriptor} opened")
        else:
            with self._open_ports_lock:
                self._open_ports.discard(port_name)
            self._logger.error(f"Failed to open adapter {self._worker_descriptor}")
            raise AdapterOpenError("Unknown error")

    def _worker_close(self) -> None:
        super()._worker_close()
        if self._port is not None:
            self._port.close()
            self._logger.info(f"Adapter {self._worker_descriptor} closed")
            self._port = None
            with self._open_ports_lock:
                self._open_ports.discard(self._worker_descriptor.port)

    async def aflush_read(self) -> None:
        await super().aflush_read()
        if self._port is not None:
            self._port.flush()

    def set_default_baudrate(self, baudrate: int) -> None:
        """
        Set baudrate

        Parameters
        ----------
        baudrate : int
        """
        if self._descriptor.set_default_baudrate(baudrate):
            self._update_descriptor()
            self.close()
            self.open()

    def _worker_write(self, data: bytes) -> None:
        super()._worker_write(data)
        if self._worker_descriptor.rts_cts:  # Experimental
            self._port.setRTS(True) # type: ignore
        if self._port is not None:
            try:
                self._port.write(data)
            except (OSError, PortNotOpenError):
                pass

    def _worker_read(self, fragment_timestamp: float) -> Fragment:
        if self._port is None:
            raise AdapterReadError("Cannot read from non-initialized port")

        try:
            data = self._port.read_all()
        except (OSError, PortNotOpenError):
            data = None

        if data is None or data == b"":
            raise AdapterReadError(
                f"Error while reading from {self._worker_descriptor}"
            )

        return Fragment(data, fragment_timestamp)

    def _selectable(self) -> HasFileno | None:
        return self._port

    # def is_opened(self) -> bool:
    #     if self._port is not None:
    #         if self._port.isOpen():  # type: ignore
    #             return True

    #     return False
