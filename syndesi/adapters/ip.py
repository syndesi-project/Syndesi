# File : ip.py
# Author : Sébastien Deriaz
# License : GPL
"""
IP adapters and backend, used to communicate with IP targets using the socket module
"""

import socket
from dataclasses import dataclass
from enum import StrEnum
from types import EllipsisType

from syndesi.tools.errors import (
    AdapterDisconnectedError,
    AdapterOpenError,
    AdapterReadError,
    AdapterWriteError,
)

from .adapter import Adapter, AsyncAdapter
from .engine import AdapterBackend, Descriptor
from .framer import BytesFramer
from .stop_conditions import Continuation, StopCondition
from .utils import Fragment, HasFileno, TimeoutParameterType


@dataclass
class IPDescriptor(Descriptor):
    """
    IP descriptor that holds ip address and port
    """

    class Transport(StrEnum):
        """
        IP Transport protocol
        """

        TCP = "TCP"
        UDP = "UDP"

        @classmethod
        def from_str(cls, transport: str) -> "IPDescriptor":
            """
            Create a Transport class from a string

            Parameters
            ----------
            transport : str
            """
            for member in cls:
                if member.value.lower() == transport.lower():
                    return member  # type: ignore # TODO : Check this
            raise ValueError(f"{transport} is not a valid {cls.__name__}")

    DETECTION_PATTERN = r"^(\d+\.\d+\.\d+\.\d+|[\w.]+):\d+:(UDP|TCP)(:server)?$"
    address: str
    transport: Transport
    port: int | None = None
    server: bool = False

    @staticmethod
    def from_string(string: str) -> "IPDescriptor":
        parts = string.split(":")
        address = parts[0]
        port = int(parts[1])
        transport = IPDescriptor.Transport(parts[2])
        server = len(parts) >= 4 and parts[3] == "server"

        return IPDescriptor(address, transport, port, server)

    def __str__(self) -> str:
        return f"{self.address}:{self.port}:{self.Transport(self.transport).value}" + (
            "(server)" if self.server else ""
        )

    def is_initialized(self) -> bool:
        """
        Return True if all attributes has been defined (not None)
        """

        return self.port is not None and self.transport is not None


BUFFER_SIZE = 65535


class IPBackend(AdapterBackend[IPDescriptor, bytes]):
    """
    Talks to an IP target through the socket module

    Parameters
    ----------
    descriptor : IPDescriptor
    """

    def __init__(self, descriptor: IPDescriptor) -> None:
        super().__init__(descriptor)

        self._socket: socket.socket | None = None

    def selectable(self) -> HasFileno | None:
        return self._socket

    def open(self, timeout: float | None) -> None:
        # Create the socket instance
        if self.descriptor.transport == IPDescriptor.Transport.TCP:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif self.descriptor.transport == IPDescriptor.Transport.UDP:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        else:
            raise AdapterOpenError("Invalid transport protocol")
        try:
            # TODO : Simulate a very long connect time (bad network) and manage timeout
            # error accordingly
            # if timeout is ...:
            #     raise BackendOpenError("Invalid timeout")
            if timeout is None:
                s.settimeout(None)
            else:
                s.settimeout(timeout)
            s.connect((self.descriptor.address, self.descriptor.port))
        except (OSError, ConnectionRefusedError, socket.gaierror) as e:
            msg = f"Failed to open adapter {self.descriptor} ({e})"
            raise AdapterOpenError(msg) from None

        # We only set the socket on success to prevent the worker thread
        # from sending events before the adapter is opened
        self._socket = s
        # self._logger.info(f"IP Adapter {self.descriptor} opened")

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def read(self, fragment_timestamp: float) -> Fragment[bytes]:
        if self._socket is None:
            raise AdapterDisconnectedError()
        try:
            data = self._socket.recv(BUFFER_SIZE)
        except (ConnectionRefusedError, OSError) as e:
            raise AdapterReadError() from e

        if data == b"":
            raise AdapterDisconnectedError()

        return Fragment(data, fragment_timestamp)

    def write(self, data: bytes) -> None:
        if self._socket is None:
            raise AdapterWriteError(f"Adapter {self.descriptor} is not connected")
        try:
            # sendall, not send : a single send is free to write only part of the data
            self._socket.sendall(data)
        except OSError as e:
            raise AdapterWriteError(
                f"Adapter {self.descriptor} couldn't write to the socket ({e})"
            ) from e

    @property
    def default_timeout(self) -> float | None:
        """Default timeout"""
        return 1.0

    # @property
    # def default_stop_conditions(self) -> list[StopCondition]:
    #     return


def default_stop_conditions() -> list[StopCondition]:
    """
    Stop-conditions of a new IP adapter

    A function, not a module level list : a stop-condition holds the state of the frame
    being assembled, so two adapters must never share the same instances
    """
    return [Continuation(continuation=0.2)]


class IP(Adapter[IPDescriptor, bytes]):
    """
    IP adapter, reads and writes bytes

    Parameters
    ----------
    address : str
    port : int or None
        None lets a protocol set its well-known port with set_default_port
    transport : {'TCP', 'UDP'}
    timeout : float, None or ...
        Time to wait for the target to respond, 1 s by default
    stop_conditions : StopCondition, list of StopCondition or ...
        When a frame is complete, Continuation(0.2) by default
    alias : str
    auto_open : bool
        Open on construction, skipped while the port is None
    """

    def __init__(
        self,
        address: str,
        port: int | None = None,
        transport: str = IPDescriptor.Transport.TCP.value,
        *,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        backend = IPBackend(
            IPDescriptor(address, IPDescriptor.Transport(transport.upper()), port)
        )
        super().__init__(
            backend,
            BytesFramer(default_stop_conditions()),
            timeout,
            stop_conditions=stop_conditions,
            alias=alias,
            auto_open=auto_open,
        )

    def set_default_port(self, port: int) -> None:
        """Set the port, unless one was given. Used by protocols with a well-known port"""
        if self.descriptor.port is None:
            self.descriptor.port = port


class AsyncIP(AsyncAdapter[IPDescriptor, bytes]):
    """
    Async IP adapter, same parameters as IP

    auto_open submits the open without waiting for it : use ``async with`` or
    ``await open()`` to wait for it, otherwise a failed open is raised by the first
    operation
    """

    def __init__(
        self,
        address: str,
        port: int | None = None,
        transport: str = IPDescriptor.Transport.TCP.value,
        *,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        backend = IPBackend(
            IPDescriptor(address, IPDescriptor.Transport(transport.upper()), port),
        )
        super().__init__(
            backend,
            BytesFramer(default_stop_conditions()),
            timeout=timeout,
            stop_conditions=stop_conditions,
            alias=alias,
            auto_open=auto_open,
        )

    def set_default_port(self, port: int) -> None:
        """Set the port, unless one was given. Used by protocols with a well-known port"""
        if self.descriptor.port is None:
            self.descriptor.port = port
