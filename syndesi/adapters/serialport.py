# File : serialport.py
# Author : Sébastien Deriaz
# License : GPL

"""
SerialPort module, allows communication with serial devices using
the OS layers (COMx, /dev/ttyUSBx or /dev/ttyACMx)

"""

from collections.abc import Callable
from dataclasses import dataclass
from types import EllipsisType

import serial
from serial.serialutil import PortNotOpenError

from syndesi.adapters.adapter_worker import AdapterEvent, HasFileno
from syndesi.component import Descriptor
from syndesi.tools.errors import AdapterOpenError, AdapterReadError
from syndesi.tools.types import NumberLike

from .adapter import Adapter
from .stop_conditions import Continuation, Fragment, StopCondition
from .timeout import Timeout


@dataclass
class SerialPortDescriptor(Descriptor):
    """
    SerialPort descriptor that holds location (COMx or /dev/ttyx) and baudrate
    """

    DETECTION_PATTERN = r"(COM\d+|/dev[/\w\d]+):\d+"
    port: str
    baudrate: int | None = None

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
        if self.baudrate is not None:
            self.baudrate = baudrate
            return True

        return False

    def __str__(self) -> str:
        return f"{self.port}:{self.baudrate}"

    def is_initialized(self) -> bool:
        return self.baudrate is not None


class SerialPort(Adapter):
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
        timeout: Timeout | NumberLike | None | EllipsisType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        rts_cts: bool = False,  # rts_cts experimental
        event_callback: Callable[[AdapterEvent], None] | None = None,
        auto_open: bool = True,
    ) -> None:
        """
        Instanciate new SerialPort adapter
        """
        descriptor = SerialPortDescriptor(port, baudrate)
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

        self._port: serial.Serial | None = None

        self.open()

        self._rts_cts = rts_cts

    def _default_timeout(self) -> Timeout:
        return Timeout(response=2, action="error")

    def _default_stop_conditions(self) -> list[StopCondition]:
        return [Continuation(0.1)]

    def _worker_open(self) -> None:
        self._worker_check_descriptor()

        if self._worker_descriptor.baudrate is None:
            raise AdapterOpenError(
                "Descriptor must be fully initialized to open the adapter"
            )

        if self._port is not None:
            self.close()

        try:
            self._port = serial.Serial(
                port=self._worker_descriptor.port,
                baudrate=self._worker_descriptor.baudrate,
                rtscts=self._rts_cts,
            )
        except serial.SerialException as e:
            if "No such file" in str(e):
                raise AdapterOpenError(
                    f"Port '{self._worker_descriptor.port}' was not found"
                ) from e
            raise AdapterOpenError("Unknown error") from e

        if self._port.isOpen():  # type: ignore
            self._logger.info(f"Adapter {self._worker_descriptor} opened")
        else:
            self._logger.error(f"Failed to open adapter {self._worker_descriptor}")
            raise AdapterOpenError("Unknown error")

    def _worker_close(self) -> None:
        if self._port is not None:
            self._port.close()
            self._logger.info(f"Adapter {self._worker_descriptor} closed")

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
        if self._rts_cts:  # Experimental
            self._port.setRTS(True)  # type: ignore
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
            self._logger.debug('Port error -> b""')
            data = None

        if data is None or data != b"":
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
