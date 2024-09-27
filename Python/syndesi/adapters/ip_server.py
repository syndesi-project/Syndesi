# ip_server.py
# Sébastien Deriaz
# 31.05.2024

import socket
from enum import Enum
from . import IP, StopCondition, Timeout
from time import time
from ..tools.types import to_bytes
from .timeout import timeout_fuse
import logging
from ..tools.log import LoggerAlias

# NOTE : The adapter is only meant to work with a single client, thus
# a IPServer class is made to handle the socket and generate IP adapters

class IPServer:
    DEFAULT_BUFFER_SIZE = 1024
    class Protocol(Enum):
        TCP = 'TCP'
        UDP = 'UDP'

    def __init__(self,
                port : int = None,
                transport : str = 'TCP',
                address : str = None,
                max_clients : int = 5,
                stop_condition = None,
                alias : str = '',
                buffer_size : int = DEFAULT_BUFFER_SIZE):

        """
        IP server adapter

        Parameters
        ----------
        port : int
            IP port. If None, the default port set with set_default_port will be used
        transport : str
            'TCP' or 'UDP'
        address : str
            Custom socket ip, None by default
        max_clients : int
            Maximum number of clients, 5 by default
        stop_condition : StopCondition
            Specify a read stop condition (None by default)
        alias : str
            Specify an alias for this adapter, '' by default
        buffer_size : int
            Socket buffer size, may be removed in the future
        """
        self._alias = alias
        self._stop_condition = stop_condition
        self._logger = logging.getLogger(LoggerAlias.ADAPTER.value)
        self._transport = self.Protocol(transport)
        if self._transport == self.Protocol.TCP:
            self._logger.info("Setting up TCP IP server adapter")
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif self._transport == self.Protocol.UDP:
            self._logger.info("Setting up UDP IP server adapter")
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        else:
            raise ValueError("Invalid protocol")

        self._address = socket.gethostname() if address is None else address
        self._port = port
        self._max_clients = max_clients
        self._opened = False
        

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
        self._logger.info(f"Listening to incoming connections on {self._address}:{self._port}")
        self._socket.bind((self._address, self._port))
        self._socket.listen(self._max_clients)
        self._opened = True

    def close(self):
        if hasattr(self, '_socket'):
            self._socket.close()
        self._logger.info("Adapter closed !")
        self._opened = False

    def get_client(self, stop_condition : StopCondition = None, timeout : Timeout = None) -> IP:
        """
        Wait for a client to connect to the server and return the corresponding adapter
        """
        if not self._opened:
            raise RuntimeError("open() must be called before getting client")
        client_socket, address = self._socket.accept()
        default_timeout = Timeout(response=None, continuation=IP.DEFAULT_CONTINUATION_TIMEOUT, total=None)
        return IP(_socket=client_socket, address=address, stop_condition=stop_condition, timeout=timeout_fuse(timeout, default_timeout))