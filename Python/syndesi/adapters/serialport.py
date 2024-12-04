import os
import serial
from threading import Thread
from typing import Union
import select
import argparse
import socket
import sys
#from collections.abc import Sequence

from .adapter import Adapter, StreamAdapter, AdapterDisconnected
from ..tools.types import to_bytes
from .stop_conditions import *
from .timeout import Timeout, timeout_fuse
from .timed_queue import TimedQueue

class SerialPort(StreamAdapter):
    def __init__(self,  
                port : str,
                baudrate : int = ...,
                timeout : Union[Timeout, float] = ...,
                stop_condition : StopCondition = ...,
                alias : str = '',
                rts_cts : bool = False): # rts_cts experimental
        """
        Serial communication adapter

        Parameters
        ----------
        port : str
            Serial port (COMx or ttyACMx)
        """            
        super().__init__(timeout=timeout, stop_condition=stop_condition, alias=alias)

        self._port_name = port
        self._baudrate_set = baudrate is not ...
        self._baudrate = baudrate
        self._logger.info(f"Setting up SerialPort adapter on {self._port_name} with baudrate={baudrate}, timeout={timeout} and stop_condition={stop_condition}")
        self._port = None

        self.open()
        

        self._rts_cts = rts_cts

    def _default_timeout(self):
        return Timeout(
                    response=2,
                    on_response='error',
                    continuation=100e-3,
                    on_continuation='return',
                    total=None,
                    on_total='error')

    def __str__(self) -> str:
        return f'Serial({self._port_name}:{self._baudrate})'

    def __repr__(self) -> str:
        return self.__str__()

    def set_baudrate(self, baudrate):
        """
        Set baudrate

        Parameters
        ----------
        baudrate : int
        """
        is_connected = self._status == self.Status.CONNECTED

        if is_connected:
            self.close()

        self._baudrate = baudrate

        if is_connected:
            self.open()

    def set_default_baudrate(self, baudrate):
        """
        Sets the default baudrate

        Parameters
        ----------
        baudrate : int
        """
        if not self._baudrate_set:
            self._baudrate = baudrate

    def flushRead(self):
        self._port.flush()
        super().flushRead()

    def open(self):
        if self._baudrate is ...:
            raise ValueError('Baudrate must be set, please use set_baudrate')

        if self._port is None:
            self._port = serial.Serial(port=self._port_name, baudrate=self._baudrate)
        elif not self._port.isOpen():
            self._port.open()
        # # Flush the input buffer
        self.flushRead()

        if self._port.isOpen():
            self._status = self.Status.CONNECTED
        else:
            self._status = self.Status.DISCONNECTED

        self._logger.info("Adapter opened !")
        if self._thread is None or not self._thread.is_alive():
            self._start_thread()

    def close(self):
        super().close()
        if self._thread is not None and self._thread.is_alive():
            try:
                self._thread.join()
            except RuntimeError:
                # If the thread cannot be joined, then so be it
                pass
        if hasattr(self, '_port'):
            # Close and the read thread will die by itself
            self._port.close()
        self._logger.info("Adapter closed !")
            
    def write(self, data : bytes):
        if self._rts_cts: # Experimental
            self._port.setRTS(True)
        data = to_bytes(data)
        if self._status == self.Status.DISCONNECTED:
            self.open()
        write_start = time()
        self._port.write(data)
        write_duration = time() - write_start
        self._logger.debug(f"Write [{write_duration*1e3:.3f}ms]: {repr(data)}")

    def _start_thread(self):
        """
        Start the read thread
        """
        super()._start_thread()
        if self._thread is None or not self._thread.is_alive():
            self._thread = Thread(target=self._read_thread, daemon=True, args=(self._port, self._read_queue, self._thread_stop_read))
            self._thread.start()

    def _read_thread(self, port : serial.Serial,read_queue : TimedQueue, stop : socket.socket):
        # On linux, it is possivle to use the select.select for both serial port and stop socketpair.
        # On Windows, this is not possible. so the port timeout is used instead.
        if sys.platform == 'win32':
            port.timeout = 0.1
        while True:
            # Check how many bytes are available
            if sys.platform == 'win32':
                ready, _, _ = select.select([stop], [], [], 0)
                if stop in ready:
                    # Stop the read thread
                    break
                else:
                    # Read data from the serialport with a timeout, if the timeout occurs, read again.
                    # This is to avoid having a crazy fast loop
                    fragment = port.read()
                    if len(fragment) > 0:
                        read_queue.put(fragment)
            else:
                ready, _, _ = select.select([self._port.fd, stop], [], [])
                if stop in ready:
                    # Stop the read thread
                    break
                elif self._port.fd in ready:
                    try:
                        in_waiting = self._port.in_waiting
                    except OSError:
                        # Input/output error, the port was disconnected
                        read_queue.put(AdapterDisconnected)
                    else:
                        fragment = port.read(in_waiting)
                        if fragment:
                            read_queue.put(fragment)

    def read(self, timeout=..., stop_condition=..., return_metrics: bool = False) -> bytes:
        """
        Read data from the device

        Parameters
        ----------
        timeout : Timeout or None
            Set a custom timeout, if None (default), the adapter timeout is used
        stop_condition : StopCondition or None
            Set a custom stop condition, if None (Default), the adapater stop condition is used
        return_metrics : bool
            Return a dictionary containing information about the read operation like
                'read_duration' : float
                'origin' : 'timeout' or 'stop_condition'
                'timeout' : Timeout.TimeoutType
                'stop_condition' : Length or Termination (StopCondition class)
                'previous_read_buffer_used' : bool
                'n_fragments' : int  
        """
        output = super().read(timeout, stop_condition, return_metrics)
        if self._rts_cts: # Experimental
            self._port.setRTS(False)
        return output