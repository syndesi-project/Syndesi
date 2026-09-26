# File : ipserver.py
# Author : Sébastien Deriaz
# License : GPL
"""
IP server adapter, accepts clients and hands them out as IP adapters

Its data type is Client, not bytes : one "frame" is one accepted connection. That is why
it uses a TrivialFramer, there is nothing to assemble
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from types import EllipsisType

from ..tools.errors import AdapterOpenError, AdapterReadError, AdapterWriteError
from .adapter import Adapter, AsyncAdapter
from .engine import AdapterBackend
from .framer import TrivialFramer
from .ip import AsyncIP, IP, IPDescriptor, default_stop_conditions
from .stop_conditions import StopCondition
from .utils import Fragment, HasFileno, TimeoutType


@dataclass
class Client:
    """A connection accepted by an IPServer, before it becomes an adapter"""

    address: str
    port: int
    socket: socket.socket

    def __str__(self) -> str:
        return f"Client on {self.address}:{self.port}"


DEFAULT_BACKLOG = 5


class IPServerBackend(AdapterBackend[IPDescriptor, Client]):
    """
    Listens on an address and accepts connections

    Parameters
    ----------
    descriptor : IPDescriptor
    backlog : int
    """

    def __init__(self, descriptor: IPDescriptor, backlog: int = DEFAULT_BACKLOG) -> None:
        super().__init__(descriptor)
        self._socket: socket.socket | None = None
        self._backlog = backlog

    def selectable(self) -> HasFileno | None:
        return self._socket

    def open(self, timeout: float | None) -> None:
        del timeout  # binding and listening don't wait for a peer
        if self.descriptor.transport == IPDescriptor.Transport.TCP:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif self.descriptor.transport == IPDescriptor.Transport.UDP:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        else:
            raise AdapterOpenError("Invalid transport protocol")

        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.descriptor.address, self.descriptor.port))
            s.listen(self._backlog)
        except (OSError, socket.gaierror) as e:
            s.close()
            raise AdapterOpenError(
                f"Failed to open server {self.descriptor} ({e})"
            ) from None

        self._socket = s

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def read(self, fragment_timestamp: float) -> Fragment[Client]:
        """Accept one connection, the reactor only calls this when one is pending"""
        if self._socket is None:
            raise AdapterReadError(f"Server {self.descriptor} is not open")
        try:
            sock, (address, port) = self._socket.accept()
        except OSError as e:
            raise AdapterReadError(f"Cannot accept on {self.descriptor} : {e}") from e
        return Fragment(Client(address, port, sock), fragment_timestamp)

    def write(self, data: Client) -> None:
        raise AdapterWriteError(
            "Cannot write to an IPServer, write to one of its clients instead"
        )

    @property
    def default_timeout(self) -> TimeoutType:
        # A server waits for clients for as long as it takes
        return None


class IPServer(Adapter[IPDescriptor, Client]):
    """
    IP server, reads accepted connections as IP adapters

    Parameters
    ----------
    address : str
        Address to listen on
    port : int or None
        Port to listen on, None lets a protocol set its default
    transport : {'TCP', 'UDP'}
    stop_conditions : StopCondition, list of StopCondition or ...
        Applied to every client adapter, not to the server itself
    backlog : int
    alias : str
    auto_open : bool

    Examples
    --------
    >>> server = IPServer('0.0.0.0', 8888)
    >>> client = server.get_client()        # an IP adapter, already connected
    >>> client.read()
    """

    def __init__(
        self,
        address: str,
        port: int | None = None,
        transport: str = IPDescriptor.Transport.TCP.value,
        *,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        backlog: int = DEFAULT_BACKLOG,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        self._client_stop_conditions = stop_conditions

        super().__init__(
            IPServerBackend(
                IPDescriptor(
                    address,
                    IPDescriptor.Transport(transport.upper()),
                    port,
                    server=True,
                ),
                backlog,
            ),
            TrivialFramer(),
            None,
            stop_conditions=...,
            alias=alias,
            auto_open=auto_open,
        )

    def set_default_port(self, port: int) -> None:
        """Set the port, unless one was given"""
        if self.descriptor.port is None:
            self.descriptor.port = port

    def get_client(self, timeout: float | None = None) -> IP:
        """
        Wait for a client to connect and return it as an IP adapter

        Parameters
        ----------
        timeout : float or None
            None waits forever
        """
        client = self.read(timeout=timeout)
        return _client_adapter(client, self._client_stop_conditions)

    def write(self, data: Client) -> None:
        raise AdapterWriteError(
            "Cannot write to an IPServer, write to one of its clients instead"
        )


class AsyncIPServer(AsyncAdapter[IPDescriptor, Client]):
    """
    Async IP server, same parameters as IPServer

    Examples
    --------
    >>> async with AsyncIPServer('0.0.0.0', 8888) as server:
    ...     client = await server.get_client()
    ...     await client.read()
    """

    def __init__(
        self,
        address: str,
        port: int | None = None,
        transport: str = IPDescriptor.Transport.TCP.value,
        *,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        backlog: int = DEFAULT_BACKLOG,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        self._client_stop_conditions = stop_conditions

        super().__init__(
            IPServerBackend(
                IPDescriptor(
                    address,
                    IPDescriptor.Transport(transport.upper()),
                    port,
                    server=True,
                ),
                backlog,
            ),
            TrivialFramer(),
            None,
            stop_conditions=...,
            alias=alias,
            auto_open=auto_open,
        )

    def set_default_port(self, port: int) -> None:
        """Set the port, unless one was given"""
        if self.descriptor.port is None:
            self.descriptor.port = port

    async def get_client(self, timeout: float | None = None) -> AsyncIP:
        """Wait for a client to connect and return it as an AsyncIP adapter"""
        client = await self.read(timeout=timeout)
        return _async_client_adapter(client, self._client_stop_conditions)

    async def write(self, data: Client) -> None:
        raise AdapterWriteError(
            "Cannot write to an IPServer, write to one of its clients instead"
        )


def _resolve(
    stop_conditions: StopCondition | list[StopCondition] | EllipsisType,
) -> StopCondition | list[StopCondition]:
    """A new set of instances per client, stop-conditions hold per-frame state"""
    if stop_conditions is ...:
        return default_stop_conditions()
    return stop_conditions


def _client_adapter(
    client: Client,
    stop_conditions: StopCondition | list[StopCondition] | EllipsisType,
) -> IP:
    return IP(
        client.address,
        client.port,
        stop_conditions=_resolve(stop_conditions),
        _socket=client.socket,
    )


def _async_client_adapter(
    client: Client,
    stop_conditions: StopCondition | list[StopCondition] | EllipsisType,
) -> AsyncIP:
    return AsyncIP(
        client.address,
        client.port,
        stop_conditions=_resolve(stop_conditions),
        _socket=client.socket,
    )
