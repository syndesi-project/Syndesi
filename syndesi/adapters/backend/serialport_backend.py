# File : serialport.py
# Author : Sébastien Deriaz
# License : GPL
"""
The SerialPort backend communicates with serial devices using the serial package
"""

import time

import serial
from serial.serialutil import PortNotOpenError, SerialException

from syndesi.tools.backend_api import AdapterBackendStatus, Fragment
from syndesi.tools.errors import AdapterConfigurationError, AdapterFailedToOpen

from .adapter_backend import AdapterBackend, HasFileno
from .descriptors import SerialPortDescriptor


class SerialPortBackend(AdapterBackend):
    """
    SerialPort backend implementation using pyserial
    """
    def __init__(self, descriptor: SerialPortDescriptor):
        """
        Serial communication adapter

        Parameters
        ----------
        port : str
            Serial port (COMx or ttyACMx)
        """
        super().__init__(descriptor=descriptor)
        self.descriptor: SerialPortDescriptor
        self._logger.info(f"Setting up SerialPort adapter {self.descriptor}")
        self._port: serial.Serial | None = None
        self._rts_cts = False

    def set_baudrate(self, baudrate: int) -> None:
        """
        Set baudrate

        Parameters
        ----------
        baudrate : int
        """
        self.descriptor.baudrate = baudrate

        if self.is_opened():
            self.close()
            self.open()

    # TODO : Check if this is still necessary, it's probably more of a frontend thing
    def set_default_baudrate(self, baudrate: int) -> None:
        """
        Sets the default baudrate

        Parameters
        ----------
        baudrate : int
        """
        self.descriptor.set_default_baudrate(baudrate)

    def flush_read(self) -> bool:
        super().flush_read()
        if self._port is None:
            return False

        self._port.flush()
        return True

    def set_rtscts(self, enabled: bool) -> None:
        """
        Enable or disable RTS/CTS
        """
        self._rts_cts = enabled
        if self.is_opened():
            self.close()
            self.open()

    def open(self) -> None:
        if self.descriptor.baudrate is None:
            raise AdapterConfigurationError("Baudrate must be set, please use set_baudrate")

        if self._port is None:
            try:
                self._port = serial.Serial(
                    port=self.descriptor.port,
                    baudrate=self.descriptor.baudrate,
                    rtscts=self._rts_cts,
                )
            except SerialException as e:
                if 'No such file' in str(e):
                    raise AdapterFailedToOpen(
                        f"No such file or directory '{self.descriptor.port}'"
                        ) from e
                raise AdapterFailedToOpen('Unknown error') from e

        elif not self._port.isOpen():  # type: ignore
            self._port.open()

        if self._port.isOpen():  # type: ignore
            self._logger.info(f"Adapter {self.descriptor} opened")
            self._status = AdapterBackendStatus.CONNECTED
        else:
            self._logger.error(f"Failed to open adapter {self.descriptor}")
            self._status = AdapterBackendStatus.DISCONNECTED
            raise AdapterFailedToOpen('Unknown error')

    def close(self) -> bool:
        super().close()
        if hasattr(self, "_port") and self._port is not None:
            # Close and the read thread will die by itself
            self._port.close()
            self._logger.info("Adapter closed")
            return True
        return False

    def write(self, data: bytes) -> bool:
        super().write(data)
        if self._port is None:
            self._logger.error(f"Cannot write to closed adapter {self.descriptor}")
            return False

        if self._rts_cts:  # Experimental
            self._port.setRTS(True)  # type: ignore
        # TODO : Implement auto open
        # if self._status == AdapterBackendStatus.DISCONNECTED:
        #     self.open()
        # write_start = time.time()
        try:
            self._port.write(data)
        except (OSError, PortNotOpenError):
            return False
        #            write_duration = time.time() - write_start
        # self._logger.debug(f"Write [{write_duration * 1e3:.3f}ms]: {repr(data)}")

        return True

    def _socket_read(self) -> Fragment:
        t = time.time()

        if self._port is None:
            self._logger.debug('Port is None -> b""')
            return Fragment(b"", t)

        try:
            data = self._port.read_all()
        except (OSError, PortNotOpenError):
            self._logger.debug('Port error -> b""')
            return Fragment(b"", t)

        # This is a test, it seems b"" happens sometimes and disconnects the adapter
        if data is not None and data != b"":
            return Fragment(data, t)
        return Fragment(b"", t)

    def is_opened(self) -> bool:
        if self._port is not None:
            if self._port.isOpen():  # type: ignore
                return True

        return False

    def selectable(self) -> HasFileno | None:
        if self._port is not None and self.is_opened():
            return self._port
        return None
