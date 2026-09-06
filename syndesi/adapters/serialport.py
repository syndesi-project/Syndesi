# File : serialport.py
# Author : Sébastien Deriaz
# License : GPL

"""
SerialPort module, allows communication with serial devices using
the OS layers (COMx, /dev/ttyUSBx or /dev/ttyACMx)

"""

import re
import sys
import threading
from dataclasses import dataclass
from enum import StrEnum
from types import EllipsisType

import serial
from serial.serialutil import PortNotOpenError
from serial.tools.list_ports import comports

from syndesi.adapters.adapterworker import AdapterWorkerInterface
from syndesi.adapters.bytesadapter import AsyncBytesAdapter, BytesAdapter
from syndesi.component import Descriptor
from syndesi.tools.errors import AdapterOpenError, AdapterReadError

from .stop_conditions import BytesFragment, Continuation, StopCondition
from .utils import Fragment, HasFileno, TimeoutParameterType


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
    # baudrate can be None to allow for default baudrate
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

class _SerialPortCommon:
    _open_ports: set[str] = set()
    #_open_ports_lock = threading.Lock()
    
    def __init__(
            self,
            *,
            port: str,
            baudrate: int | None = None,
            bytesize: int = 8,
            stopbits: int = 1,
            parity: str = Parity.NONE.value,
            rts_cts: bool = False,
            xon_xoff: bool = False,
            dsr_dtr: bool = False
            ) -> None:

        self._port: serial.Serial | None = None
        self._descriptor = SerialPortDescriptor(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            stopbits=stopbits,
            parity=parity,
            rts_cts=rts_cts,
            dsr_dtr=dsr_dtr,
            xon_xoff=xon_xoff,
        )


    @staticmethod
    def list_ports() -> list[str]:
        """
        List available serial ports (excluding ttyn and ttySn on linux) as
        usable paths / names
        """
        if sys.platform in ["linux", "linux2", "darwin"]:
            # linux
            # Return all ports except ttyn, ttySn, etc...
            return [p.device for p in comports() if not re.match(r'ttyS?(\d+)', p.name)]

        if sys.platform == "win32":
            # Windows
            return [p.device for p in comports()]

        raise RuntimeError(f"Invalid platform : {sys.platform}")

    @property
    def descriptor(self) -> SerialPortDescriptor:
        return self._descriptor

    @property
    def default_timeout(self) -> float | None:
        """Default timeout"""
        return 2.0

    @staticmethod
    def _default_stop_conditions() -> list[StopCondition]:
        return [Continuation(0.1)]

    def _worker_open(self) -> None:
        if self._descriptor.baudrate is None:
            raise AdapterOpenError(
                "Descriptor must be fully initialized to open the adapter"
            )

        if self._port is not None:
            self._worker_close()

        try:
            self._port = serial.Serial(
                port=self._descriptor.port,
                baudrate=self._descriptor.baudrate,
                rtscts=self._descriptor.rts_cts,
                bytesize=self._descriptor.bytesize,
                parity=self._descriptor.parity,
                stopbits=self._descriptor.stopbits,
                xonxoff=self._descriptor.xon_xoff,
                dsrdtr=self._descriptor.dsr_dtr,
                exclusive=True,
            )
        except serial.SerialException as e:
            # with self._open_ports_lock:
            #    self._open_ports.discard(self._descriptor.port)
            if "No such file" in str(e):
                raise AdapterOpenError(
                    f"Port '{self._descriptor.port}' was not found"
                ) from e
            raise AdapterOpenError(f"SerialPort open error : {str(e)}") from None

        if not self._port.isOpen():  # type: ignore
            #self._logger.info(f"Adapter {self._descriptor} opened")
        #else:
            # with self._open_ports_lock:
            #    self._open_ports.discard(self._descriptor.port)
            raise AdapterOpenError("Unknown error")

    def _worker_close(self) -> None:
        #super()._worker_close()
        if self._port is not None:
            self._port.close()
            #self._logger.info(f"Adapter {self._descriptor} closed")
            self._port = None
            #with self._open_ports_lock:
            self._open_ports.discard(self._descriptor.port)

    def set_default_baudrate(self, baudrate: int) -> None:
        """
        Set baudrate

        Parameters
        ----------
        baudrate : int
        """
        if self._descriptor.set_default_baudrate(baudrate):
            self._worker_close()
            self._worker_open()

    def _worker_write(self, data: bytes) -> None:
        if self._descriptor.rts_cts:  # Experimental
            self._port.setRTS(True)  # type: ignore
        if self._port is not None:
            try:
                self._port.write(data)
            except (OSError, PortNotOpenError):
                pass

    def _worker_read(self, fragment_timestamp: float) -> BytesFragment:
        if self._port is None:
            raise AdapterReadError("Cannot read from non-initialized port")

        try:
            data = self._port.read_all()
        except (OSError, PortNotOpenError):
            data = None

        if data is None or data == b"":
            raise AdapterReadError(f"Error while reading from {self._descriptor}")

        return Fragment(data, fragment_timestamp)

    def _selectable(self) -> HasFileno | None:
        return self._port

class SerialPort(_SerialPortCommon, BytesAdapter):
    """
    Serial communication adapter

    Parameters
    ----------
    port : str
        Serial port (COMx or ttyACMx)
    baudrate : int
        Baudrate
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
        _SerialPortCommon.__init__(
            self,
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            stopbits=stopbits,
            parity=parity,
            rts_cts=rts_cts,
            xon_xoff=xon_xoff,
            dsr_dtr=dsr_dtr
        )
        BytesAdapter.__init__(
            self,
            timeout=timeout,
            stop_conditions=stop_conditions,
            alias=alias,
            auto_open=auto_open
        )

        self._logger.info(
            f"Setting up SerialPort adapter {self._descriptor}, \
                timeout={timeout} and stop_conditions={stop_conditions}"
        )

    def clear_read_buffer(self) -> None:
        super().clear_read_buffer()
        if self._port is not None:
            self._port.flush()

class AsyncSerialPort(_SerialPortCommon, AsyncBytesAdapter):
    """
    The AsyncSerialPort class allows asynchronous communication with serial devices
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
        _SerialPortCommon.__init__(
            self,
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            stopbits=stopbits,
            parity=parity,
            rts_cts=rts_cts,
            xon_xoff=xon_xoff,
            dsr_dtr=dsr_dtr
        )
        AsyncBytesAdapter.__init__(
            self,
            timeout=timeout,
            stop_conditions=stop_conditions,
            alias=alias,
            auto_open=auto_open
        )

        self._logger.info(
            f"Setting up SerialPort adapter {self._descriptor}, \
                timeout={timeout} and stop_conditions={stop_conditions}"
        )

    async def clear_read_buffer(self) -> None:
        await super().clear_read_buffer()
        if self._port is not None:
            self._port.flush()