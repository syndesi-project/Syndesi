import os
import serial
from threading import Thread
from typing import Union
import select
import argparse
import socket
import sys
#from collections.abc import Sequence

from .adapter import Adapter, AdapterDisconnected
from ..tools.types import to_bytes
from .stop_conditions import *
from .timeout import Timeout
from .timed_queue import TimedQueue
#from ..cli import shell
from ..tools.others import DEFAULT

DEFAULT_TIMEOUT = Timeout(
                    response=1,
                    on_response='error',
                    continuation=200e-3,
                    on_continuation='return',
                    total=None,
                    on_total='error')




class SerialPort(Adapter):
    def __init__(self,  
                port : str,
                baudrate : int,
                timeout : Union[Timeout, float] = DEFAULT,
                stop_condition : StopCondition = DEFAULT,
                rts_cts : bool = False): # rts_cts experimental
        """
        Serial communication adapter

        Parameters
        ----------
        port : str
            Serial port (COMx or ttyACMx)
        """
        if timeout == DEFAULT:
            timeout = DEFAULT_TIMEOUT
            
        super().__init__(timeout=timeout, stop_condition=stop_condition)
        self._logger.info(f"Setting up SerialPort adapter timeout:{timeout}, stop_condition:{stop_condition}")
        self._port_name = port
        self._baudrate = baudrate
        self._port = serial.Serial(port=self._port_name, baudrate=self._baudrate)
        if self._port.isOpen():
            self._status = self.Status.CONNECTED
        else:
            self._status = self.Status.DISCONNECTED

        self._rts_cts = rts_cts

    def flushRead(self):
        self._port.flush()

    def open(self):
        self._port.open()
        # Flush the input buffer
        buf = b'0'
        while buf:
            buf = os.read(self._port.fd)
        self._logger.info("Adapter opened !")

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
        self._logger.debug("Starting read thread...")
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
                    data = port.read()
                    if len(data) > 0:
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

    def read(self, timeout=DEFAULT, stop_condition=DEFAULT, return_metrics: bool = False) -> bytes:
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

    def query(self, data : Union[bytes, str], timeout=None, stop_condition=None, return_metrics : bool = False):
        self.flushRead()
        self.write(data)
        return self.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)

    # def shell_parse(inp: str):
    #     parser = argparse.ArgumentParser(
    #     prog='',
    #     description='Serial port shell parser',
    #     epilog='')
    #     # Parse subcommand    
    #     parser.add_argument('--' + shell.Arguments.PORT.value, type=str)
    #     parser.add_argument('--' + shell.Arguments.BAUDRATE.value, type=int)
    #     parser.add_argument('--' + shell.Arguments.ENABLE_RTS_CTS.value, action='store_true')
    #     args = parser.parse_args(inp.split())

    #     return {
    #         'port' : getattr(args, shell.Arguments.PORT.value),
    #         'baudrate' : getattr(args, shell.Arguments.BAUDRATE.value),
    #         'rts_cts' : bool(getattr(args, shell.Arguments.ENABLE_RTS_CTS.value))
    #     }