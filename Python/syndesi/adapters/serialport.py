from .adapter import Adapter
import serial
from ..tools.types import to_bytes
from .stop_conditions import *
from .timeout import Timeout
from .timed_queue import TimedQueue
from threading import Thread
from typing import Union
import select
import argparse
from ..tools import shell
from collections.abc import Sequence

# From pyserial - serialposix.py
import fcntl
import termios
import struct
if hasattr(termios, 'TIOCINQ'):
    TIOCINQ = termios.TIOCINQ
else:
    TIOCINQ = getattr(termios, 'FIONREAD', 0x541B)
TIOCM_zero_str = struct.pack('I', 0)
import os

DEFAULT_TIMEOUT = Timeout(response=0.5, continuation=10e-3, total=None)

class SerialPort(Adapter):
    def __init__(self,  
                port : str,
                baudrate : int,
                timeout : Union[Timeout, float] = DEFAULT_TIMEOUT,
                stop_condition : StopCondition = None,
                rts_cts : bool = False): # rts_cts experimental
        """
        Serial communication adapter

        Parameters
        ----------
        port : str
            Serial port (COMx or ttyACMx)
        """
        super().__init__(timeout=timeout, stop_condition=stop_condition)
        self._logger.info("Setting up SerialPort adapter")
        self._port = serial.Serial(port=port, baudrate=baudrate)
        if self._port.isOpen():
            self._status = self.Status.CONNECTED
        else:
            self._status = self.Status.DISCONNECTED

        self._rts_cts = rts_cts
        
        self._stop_event_pipe, self._stop_event_pipe_write = os.pipe()

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
        if self._thread is not None and self._thread.is_alive():
            os.write(self._stop_event_pipe_write, b'1')
            self._thread.join()
        if hasattr(self, '_port'):
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
        self._logger.debug(f"Written [{write_duration*1e3:.3f}ms]: {repr(data)}")

    def _start_thread(self):
        """
        Start the read thread
        """
        self._logger.debug("Starting read thread...")
        if self._thread is None or not self._thread.is_alive():
            self._thread = Thread(target=self._read_thread, daemon=True, args=(self._port, self._read_queue, self._stop_event_pipe))
            self._thread.start()

    def _read_thread(self, port : serial.Serial , read_queue : TimedQueue, stop_event_pipe):
        while True:
            # It looks like using the raw implementation of port.in_waiting and port.read is better, there's no more warnings
            # Equivalent of port.in_waiting :
            in_waiting = struct.unpack('I', fcntl.ioctl(port.fd, TIOCINQ, TIOCM_zero_str))[0]
            if in_waiting == 0:
                ready, _, _ = select.select([port.fd, stop_event_pipe], [], [], None)
                if stop_event_pipe in ready:
                    # Stop
                    break
            # Else, read as many bytes as possible
            fragment = os.read(port.fd, 1000) # simplified version of port.read()
            if fragment:
                read_queue.put(fragment)        

    def read(self, timeout=None, stop_condition=None, return_metrics: bool = False) -> bytes:
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

    def shell_parse(inp: str):
        parser = argparse.ArgumentParser(
        prog='',
        description='Serial port shell parser',
        epilog='')
        # Parse subcommand    
        parser.add_argument('--' + shell.Arguments.PORT.value, type=str)
        parser.add_argument('--' + shell.Arguments.BAUDRATE.value, type=int)
        parser.add_argument('--' + shell.Arguments.ENABLE_RTS_CTS.value, action='store_true')
        args = parser.parse_args(inp.split())

        return {
            'port' : getattr(args, shell.Arguments.PORT.value),
            'baudrate' : getattr(args, shell.Arguments.BAUDRATE.value),
            'rts_cts' : bool(getattr(args, shell.Arguments.ENABLE_RTS_CTS.value))
        }