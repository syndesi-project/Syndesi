import socket
from enum import Enum
from .adapter import Adapter
from ..tools.types import to_bytes
from .timeout import Timeout
from threading import Thread
from .timed_queue import TimedQueue
from typing import Union
from time import time

DEFAULT_RESPONSE_TIMEOUT = 1
DEFAULT_CONTINUATION_TIMEOUT = 1e-3
DEFAULT_TOTAL_TIMEOUT = 5

DEFAULT_BUFFER_SIZE = 1024

DEFAULT_TIMEOUT = Timeout(
                    response=DEFAULT_RESPONSE_TIMEOUT,
                    continuation=DEFAULT_CONTINUATION_TIMEOUT,
                    total=DEFAULT_TOTAL_TIMEOUT)

class IP(Adapter):
    class Protocol(Enum):
        TCP = 'TCP'
        UDP = 'UDP'
    def __init__(self,
                address : str,
                port : int = None,
                transport : str = 'TCP',
                timeout : Union[Timeout, float] = DEFAULT_TIMEOUT,
                stop_condition = None,
                alias : str = '',
                buffer_size : int = DEFAULT_BUFFER_SIZE):
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
        """
        super().__init__(alias=alias, timeout=timeout, stop_condition=stop_condition)
        self._transport = self.Protocol(transport)
        if self._transport == self.Protocol.TCP:
            self._logger.info("Setting up TCP IP adapter")
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif self._transport == self.Protocol.UDP:
            self._logger.info("Setting up UDP IP adapter")
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        else:
            raise ValueError("Invalid protocol")
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
        if self._port is None:
            raise ValueError(f"Cannot open adapter without specifying a port")
        self._socket.connect((self._address, self._port))
        self._status = self.Status.CONNECTED
        self._logger.info("Adapter opened !")

    def close(self):
        if hasattr(self, '_socket'):
            self._socket.close()
        self._logger.info("Adapter closed !")
            
    def write(self, data : Union[bytes, str]):
        data = to_bytes(data)
        if self._status == self.Status.DISCONNECTED:
            self._logger.info("Adapter is closed, opening...")
            self.open()
        write_start = time()
        self._socket.send(data)
        write_duration = time() - write_start
        self._logger.debug(f"Written [{write_duration*1e3:.3f}ms]: {repr(data)}")

    def _read_thread(self, socket : socket.socket, read_queue : TimedQueue):
        while True:
            try:
                payload = socket.recv(self._buffer_size)
                if len(payload) == self._buffer_size and self._transport == self.Protocol.UDP:
                    self._logger.warning("Warning, inbound UDP data may have been lost (max buffer size attained)")
            except OSError:
                break
            if not payload:
                break
            read_queue.put(payload)

    def _start_thread(self):
        self._logger.debug("Starting read thread...")
        self._thread = Thread(target=self._read_thread, daemon=True, args=(self._socket, self._read_queue))
        self._thread.start()

    def query(self, data : Union[bytes, str], timeout=None, stop_condition=None, return_metrics : bool = False):
        self.flushRead()
        self.write(data)
        return self.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)