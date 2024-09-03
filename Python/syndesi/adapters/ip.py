import socket
from enum import Enum
from .adapter import Adapter, AdapterDisconnected
from ..tools.types import to_bytes
from .timeout import Timeout, timeout_fuse
from .stop_conditions import StopCondition
from threading import Thread
from .timed_queue import TimedQueue
from typing import Union
from time import time
import argparse
#from ..cli import shell
from ..tools.others import DEFAULT
import select

class IP(Adapter):
    DEFAULT_TIMEOUT = Timeout(
                        response=2,
                        on_response='error',
                        continuation=100e-3,
                        on_continuation='return',
                        total=5,
                        on_total='error')
    DEFAULT_BUFFER_SIZE = 1024
    class Protocol(Enum):
        TCP = 'TCP'
        UDP = 'UDP'

    def __init__(self,
                address : str,
                port : int = None,
                transport : str = 'TCP',
                timeout : Union[Timeout, float] = DEFAULT,
                stop_condition : StopCondition = DEFAULT,
                alias : str = '',
                buffer_size : int = DEFAULT_BUFFER_SIZE,
                _socket : socket.socket = None):
        """
        IP stack adapter

        Parameters
        ----------
        address : str
            IP description
        port : int
            IP port
        transport : str
            'TCP' or 'UDP'
        timeout : Timeout | float
            Specify communication timeout
        stop_condition : StopCondition
            Specify a read stop condition (None by default)
        alias : str
            Specify an alias for this adapter, '' by default
        buffer_size : int
            Socket buffer size, may be removed in the future
        socket : socket.socket
            Specify a custom socket, this is reserved for server application
        """
        if timeout == DEFAULT:
            timeout = self.DEFAULT_TIMEOUT
        else:
            timeout = timeout_fuse(timeout, self.DEFAULT_TIMEOUT)
        
        super().__init__(alias=alias, timeout=timeout, stop_condition=stop_condition)
        self._transport = self.Protocol(transport)
        self._is_server = _socket is not None

        self._logger.info(f"Setting up {self._transport.value} IP adapter ({'server' if self._is_server else 'client'})")

        if self._is_server:
            # Server
            self._socket = _socket
            self._status = self.Status.CONNECTED
        elif self._transport == self.Protocol.TCP:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif self._transport == self.Protocol.UDP:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        self._address = address
        self._port = port
        self._buffer_size = buffer_size

    def set_default_port(self, port):
        """
        Sets IP port if no port has been set yet.

        This way, the user can leave the port empty
        and the driver/protocol can specify it later
        
        Parameters
        ----------
        port : int
        """
        if self._port is None:
            self._port = port

    def open(self):
        if self._is_server:
            raise SystemError("Cannot open server socket. It must be passed already opened")
        if self._port is None:
            raise ValueError(f"Cannot open adapter without specifying a port")

        self._logger.debug(f"Adapter {self._alias} connect to ({self._address}, {self._port})")
        self._socket.connect((self._address, self._port))
        self._status = self.Status.CONNECTED
        self._logger.info(f"Adapter {self._alias} opened !")

    def close(self):
        super().close()
        if self._thread is not None and self._thread.is_alive():
            try:
                self._thread.join()
            except RuntimeError:
                # If the thread cannot be joined, then so be it
                pass
        if hasattr(self, '_socket'):
            self._socket.close()
        self._logger.info("Adapter closed !")
        self._status = self.Status.DISCONNECTED
            
    def write(self, data : Union[bytes, str]):
        data = to_bytes(data)
        if self._status == self.Status.DISCONNECTED:
            self._logger.info(f"Adapter {self._alias} is closed, opening...")
            self.open()
        write_start = time()
        self._socket.send(data)
        write_duration = time() - write_start
        self._logger.debug(f"Write [{write_duration*1e3:.3f}ms]: {repr(data)}")

    def _start_thread(self):
        self._logger.debug("Starting read thread...")
        if self._thread is None or not self._thread.is_alive():
            self._thread = Thread(target=self._read_thread, daemon=True, args=(self._socket, self._read_queue, self._thread_stop_read))
            self._thread.start()

    # # EXPERIMENTAL
    # def read_thread_alive(self):
    #     return self._thread.is_alive()

    def _read_thread(self, socket : socket.socket, read_queue : TimedQueue, stop : socket.socket):
        # Using select.select works on both Windows and Linux as long as the inputs are all sockets
        while True: # TODO : Add stop_pipe ? Maybe it was removed ?
            
            try:
                ready, _, _ = select.select([socket, stop], [], [])
            except ValueError:
                # File desctiptor is s negative integer
                read_queue.put(AdapterDisconnected())
            else:
                if stop in ready:
                    # Stop the thread
                    stop.recv(1)
                    break
                elif socket in ready:
                    # Read from the socket
                    try:
                        payload = socket.recv(self._buffer_size)
                    except ConnectionRefusedError:
                        # TODO : Check if this is the right way of doing it
                        read_queue.put(AdapterDisconnected())
                    else:
                        if len(payload) == self._buffer_size and self._transport == self.Protocol.UDP:
                            self._logger.warning("Warning, inbound UDP data may have been lost (max buffer size attained)")
                        if payload == b'':
                            read_queue.put(AdapterDisconnected())
                            break
                        else:
                            read_queue.put(payload)

    def query(self, data : Union[bytes, str], timeout=None, stop_condition=None, return_metrics : bool = False):
        if self._is_server:
            raise SystemError("Cannot query on server adapters")
        self.flushRead()
        self.write(data)
        return self.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)
    
    