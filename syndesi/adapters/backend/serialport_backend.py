# File : serialport.py
# Author : Sébastien Deriaz
# License : GPL
#
# The SerialPort backend communicates with serial devices using the serial package

import time

import serial
from serial.serialutil import PortNotOpenError

from syndesi.tools.backend_api import AdapterBackendStatus, Fragment

from .adapter_backend import AdapterBackend, HasFileno
from .descriptors import SerialPortDescriptor


class SerialPortBackend(AdapterBackend):
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

        self.open()

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
        else:
            self._port.flush()
            return True

    def set_rtscts(self, enabled: bool) -> None:
        self._rts_cts = enabled
        if self.is_opened():
            self.close()
            self.open()

    def open(self) -> bool:
        if self.descriptor.baudrate is None:
            raise ValueError("Baudrate must be set, please use set_baudrate")

        if self._port is None:
            self._port = serial.Serial(
                port=self.descriptor.port,
                baudrate=self.descriptor.baudrate,
                rtscts=self._rts_cts,
            )
        elif not self._port.isOpen():  # type: ignore
            self._port.open()

        if self._port.isOpen():  # type: ignore
            self._logger.info(f"Adapter {self.descriptor} opened")
            self._status = AdapterBackendStatus.CONNECTED
            return True
        else:
            self._logger.error(f"Failed to open adapter {self.descriptor}")
            self._status = AdapterBackendStatus.DISCONNECTED
            return False

    def close(self) -> bool:
        super().close()
        if hasattr(self, "_port") and self._port is not None:
            # Close and the read thread will die by itself
            self._port.close()
            self._logger.info("Adapter closed")
            return True
        else:
            return False

    def write(self, data: bytes) -> bool:
        super().write(data)
        if self._port is None:
            self._logger.error(f"Cannot write to closed adapter {self.descriptor}")
            return False
        else:
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
        else:
            try:
                data = self._port.read_all()
            except (OSError, PortNotOpenError):
                self._logger.debug('Port error -> b""')
                return Fragment(b"", t)
            else:
                # This is a test, it seems b"" happens sometimes and disconnects the adapter
                if data is not None and data != b"":
                    return Fragment(data, t)
                else:
                    return Fragment(b"", t)
                    # self._logger.debug('Data is none -> b""')
                # else:
                #     self._logger.debug(f'{data=}')

    # def _start_thread(self):
    #     """
    #     Start the read thread
    #     """
    #     #super()._start_thread()
    #     if self._thread is None or not self._thread.is_alive():
    #         self._thread = Thread(
    #             target=self._read_thread,
    #             daemon=True,
    #             args=(self._port, self._read_queue, self._thread_commands_read),
    #         )
    #         self._thread.start()

    # def _read_thread(
    #     self,
    #     port: serial.Serial,
    #     read_queue: TimedQueue,
    #     thread_commands: socket.socket,
    # ):
    #     # On linux, it is possivle to use the select.select for both serial port and stop socketpair.
    #     # On Windows, this is not possible. so the port timeout is used instead.
    #     if sys.platform == "win32":
    #         port.timeout = 0.1
    #     while True:
    #         # Check how many bytes are available
    #         if sys.platform == "win32":
    #             ready, _, _ = select.select([thread_commands], [], [], 0)
    #             if thread_commands in ready:
    #                 # Stop the read thread
    #                 break
    #             else:
    #                 # Read data from the serialport with a timeout, if the timeout occurs, read again.
    #                 # This is to avoid having a crazy fast loop
    #                 fragment = port.read()
    #                 if len(fragment) > 0:
    #                     read_queue.put(fragment)
    #         else:
    #             ready, _, _ = select.select([self._port.fd, thread_commands], [], [])
    #             if thread_commands in ready:
    #                 command = self.ThreadCommands(thread_commands.recv(1))
    #                 if command == self.ThreadCommands.STOP:
    #                     # Stop the read thread
    #                     break
    #             elif self._port.fd in ready:
    #                 try:
    #                     in_waiting = self._port.in_waiting
    #                 except OSError:
    #                     # Input/output error, the port was disconnected
    #                     read_queue.put(AdapterDisconnected)
    #                 else:
    #                     fragment = port.read(in_waiting)
    #                     if fragment:
    #                         read_queue.put(fragment)

    # def read(
    #     self, timeout=..., stop_condition=..., full_output: bool = False
    # ) -> bytes:
    #     """
    #     Read data from the device

    #     Parameters
    #     ----------
    #     timeout : Timeout or None
    #         Set a custom timeout, if None (default), the adapter timeout is used
    #     stop_condition : StopCondition or None
    #         Set a custom stop condition, if None (Default), the adapater stop condition is used
    #     full_output : bool
    #         Return a dictionary containing information about the read operation like
    #             'read_duration' : float
    #             'origin' : 'timeout' or 'stop_condition'
    #             'timeout' : Timeout.TimeoutType
    #             'stop_condition' : Length or Termination (StopCondition class)
    #             'previous_read_buffer_used' : bool
    #             'n_fragments' : int
    #     """
    #     output = super().read(timeout, stop_condition, full_output)
    #     if self._rts_cts:  # Experimental
    #         self._port.setRTS(False)
    #     return output

    def is_opened(self) -> bool:
        if self._port is not None:
            if self._port.isOpen():  # type: ignore
                return True

        return False

    def selectable(self) -> HasFileno | None:
        if self._port is not None and self.is_opened():
            return self._port
        else:
            return None
