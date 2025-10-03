# File : serialport.py
# Author : Sébastien Deriaz
# License : GPL

from collections.abc import Callable
from types import EllipsisType

from syndesi.adapters.backend.adapter_backend import AdapterSignal
from syndesi.tools.types import NumberLike

from .adapter import Adapter
from .backend.descriptors import SerialPortDescriptor
from .stop_condition import StopCondition
from .timeout import Timeout


class SerialPort(Adapter):
    def __init__(
        self,
        port: str,
        baudrate: int | None = None,
        timeout: Timeout | NumberLike | None | EllipsisType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        rts_cts: bool = False,  # rts_cts experimental
        event_callback: Callable[[AdapterSignal], None] | None = None,
        backend_address: str | None = None,
        backend_port: int | None = None,
    ) -> None:
        """
        Serial communication adapter

        Parameters
        ----------
        port : str
            Serial port (COMx or ttyACMx)
        """
        descriptor = SerialPortDescriptor(port, baudrate)
        super().__init__(
            descriptor=descriptor,
            timeout=timeout,
            stop_conditions=stop_conditions,
            alias=alias,
            event_callback=event_callback,
            backend_address=backend_address,
            backend_port=backend_port,
        )
        self.descriptor: SerialPortDescriptor

        self._logger.info(
            f"Setting up SerialPort adapter {self.descriptor}, timeout={timeout} and stop_conditions={self._stop_conditions}"
        )

        self.open()

        self._rts_cts = rts_cts

    def _default_timeout(self) -> Timeout:
        return Timeout(response=2, action="error")

    def set_baudrate(self, baudrate: int) -> None:
        """
        Set baudrate

        Parameters
        ----------
        baudrate : int
        """
        if self.descriptor.set_default_baudrate(baudrate):
            self.close()
            self.open()

    def open(self) -> None:
        if self.descriptor.baudrate is None:
            raise ValueError("Baudrate must be set, please use set_baudrate")
        super().open()

    def close(self, force: bool = False) -> None:
        super().close(force)
        self._logger.info("Adapter closed")
