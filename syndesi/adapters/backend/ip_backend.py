# File : ip.py
# Author : Sébastien Deriaz
# License : GPL
#
# The IP backend communicates with TCP or UDP capable hosts using the IP layer

import socket
import time
from typing import cast

import _socket

from ...tools.backend_api import AdapterBackendStatus, Fragment
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

    def open(self) -> bool:
        output = False
        if self._status == AdapterBackendStatus.DISCONNECTED:
            if self.descriptor.port is None:  # TODO : Check if this is even possible
                raise ValueError("Cannot open adapter without specifying a port")

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
                    raise ValueError(
                        f"Invalid transport protocol : {self.descriptor.transport}"
                    )
            try:
                self._socket.settimeout(
                    0.5
                )  # TODO : Configure this cleanly, it has to be less than the receive timeout of the frontend
                self._socket.connect((self.descriptor.address, self.descriptor.port))
            except OSError as e:  # TODO : Maybe change the exception ?
                self._logger.error(f"Failed to open adapter {self.descriptor} : {e}")
            else:
                self._status = AdapterBackendStatus.CONNECTED
                self._logger.info(f"IP Adapter {self.descriptor} opened")
                output = True
        else:
            self._logger.info(f"Adapter {self.descriptor} already openend")
            output = True

        return output

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
            self._socket.send(data)
        except (BrokenPipeError, OSError) as e:
            # Socket has been disconnected by the remote peer
            self._logger.error(f"Failed to write to adapter {self.descriptor} ({e})")
            self.close()
            return False
        else:
            return True

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
