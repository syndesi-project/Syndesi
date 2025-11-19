# File : ip.py
# Author : Sébastien Deriaz
# License : GPL
#
# The IP backend communicates with TCP or UDP capable hosts using the IP layer

import socket
import time
from typing import cast

import _socket

from syndesi.tools.errors import AdapterConfigurationError, AdapterFailedToOpen

from ...tools.backend_api import (
    DEFAULT_ADAPTER_OPEN_TIMEOUT,
    AdapterBackendStatus,
    Fragment,
)
from .adapter_backend import AdapterBackend, HasFileno
from .descriptors import IPDescriptor


class IPBackend(AdapterBackend):
    BUFFER_SIZE = 65507
    # _DEFAULT_BUFFER_SIZE = 1024
    # DEFAULT_TIMEOUT = TimeoutBackend(
    #     response=5,
    #     action="error"
    # )
    DEFAULT_STOP_CONDITION = None

    def __init__(self, descriptor: IPDescriptor):
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
        buffer_size : int
            Socket buffer size, may be removed in the future
        socket : socket.socket
            Specify a custom socket, this is reserved for server application
        """
        super().__init__(descriptor=descriptor)
        self.descriptor: IPDescriptor

        self._logger.info(f"Setting up {self.descriptor} adapter ")

        self._socket: _socket.socket | None = None

    def selectable(self) -> HasFileno | None:
        return self._socket

    def open(self):
        if self._status == AdapterBackendStatus.CONNECTED:
            self._logger.warning(f"Adapter {self.descriptor} already openend")
            return
        
        if self.descriptor.port is None:
            raise AdapterConfigurationError("Cannot open adapter without specifying a port")

        if self._socket is None:
            if self.descriptor.transport == IPDescriptor.Transport.TCP:
                self._socket = cast(
                    _socket.socket,
                    socket.socket(socket.AF_INET, socket.SOCK_STREAM),
                )
            elif self.descriptor.transport == IPDescriptor.Transport.UDP:
                self._socket = cast(
                    _socket.socket, socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                )
            else:
                raise AdapterConfigurationError(
                    f"Invalid transport protocol : {self.descriptor.transport}"
                )
        try:
            self._socket.settimeout(DEFAULT_ADAPTER_OPEN_TIMEOUT)
            self._socket.connect((self.descriptor.address, self.descriptor.port))
        except OSError as e:
            self._logger.error(f"Failed to open adapter {self.descriptor} : {e}")
            raise AdapterFailedToOpen(str(e))
        else:
            self._status = AdapterBackendStatus.CONNECTED
            self._logger.info(f"IP Adapter {self.descriptor} opened")

    def close(self) -> bool:
        super().close()

        self._status = AdapterBackendStatus.DISCONNECTED
        if self._socket is not None:
            self._socket.close()
            self._socket = None
            self._logger.info(f"Adapter {self.descriptor} closed")
            return True
        else:
            self._logger.error(f"Failed to close adapter {self.descriptor}")
            return False

    def write(self, data: bytes) -> bool:
        super().write(data)

        # TODO : Manage adapter reopen
        # if self._status == AdapterBackendStatus.DISCONNECTED:
        #     self._logger.info("Adapter is closed, opening...")
        #     self.open()

        # Socket send
        if self._socket is None:
            self._logger.error(f"Cannot write to closed adapter {self.descriptor}")
            return False
        try:
            ok = self._socket.send(data) == len(data)
        except (BrokenPipeError, OSError):
            # Socket has been disconnected by the remote peer
            ok = False

        if not ok:
            self._logger.error(f"Failed to write to adapter {self.descriptor}")
            self.close()

        return ok

    def _socket_read(self) -> Fragment:
        # This function is called only if the socket was ready
        t = time.time()
        if self._socket is None:
            return Fragment(b"", t)
        else:
            try:
                fragment = Fragment(self._socket.recv(self.BUFFER_SIZE), t)
            except (ConnectionRefusedError, OSError):
                fragment = Fragment(b"", t)

            if fragment.data == b"":
                # Socket disconnected
                self._logger.debug("## Socket disconnected")
                self.close()

        return fragment

    def is_opened(self) -> bool:
        return self._status == AdapterBackendStatus.CONNECTED
