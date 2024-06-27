import os
import serial
from threading import Thread
from typing import Union
import select
import argparse
#from collections.abc import Sequence

from .adapter import Adapter
from ..tools.types import to_bytes
from .stop_conditions import *
from .timeout import Timeout
from .timed_queue import TimedQueue
from ..tools import shell
from ..tools.others import DEFAULT

DEFAULT_TIMEOUT = Timeout(response=1, continuation=200e-3, total=None)

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
        self._port = serial.Serial(port=port, baudrate=baudrate)
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
        self._logger.debug(f"Written [{write_duration*1e3:.3f}ms]: {repr(data)}")

    def _start_thread(self):
        """
        Start the read thread
        """
        self._logger.debug("Starting read thread...")
        if self._thread is None or not self._thread.is_alive():
            self._thread = Thread(target=self._read_thread, daemon=True, args=(self._port, self._read_queue))
            self._thread.start()

    def _read_thread(self, port : serial.Serial , read_queue : TimedQueue):
        # NOTE : There should be some way to kill the thread, maybe check for an error on in_waiting but couldn't find it so far
        while True:
            # Check how many bytes are available
            in_waiting = self._port.in_waiting # This is a temporary fix to get windows compatiblity back, an error might pop up
            if in_waiting > 0:
                # Read those bytes
                fragment = port.read(in_waiting)
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