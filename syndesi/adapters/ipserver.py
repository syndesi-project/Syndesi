# NOT YET PORTED to the backend/framer/engine/reactor architecture.
# This module still targets the removed Component/Adapter classes. It is kept
# as a reference while it gets ported, and excluded from the checkers until then
# mypy: ignore-errors
# pylint: skip-file
# ruff: noqa
# File : ipserver.py
# Author : Sébastien Deriaz
# License : GPL
"""
IP Server adapter, used to manage IP clients
"""

import queue
import socket
from collections.abc import Callable
from dataclasses import dataclass
from types import EllipsisType

from syndesi.adapters.adapter import Adapter
from syndesi.adapters.adapterworker import AdapterEvent, AdapterFrameEvent, AdapterWorker
from syndesi.adapters.stop_conditions import Continuation, StopCondition
from syndesi.tools.errors import AdapterOpenError, AdapterReadError

from .ip import IP, IPDescriptor
from .utils import Fragment, HasFileno


@dataclass
class Client:
    """Data packet received or sent to an IPServer client"""

    address: str
    port: int
    socket: socket.socket

    def __str__(self) -> str:
        return f"Client on {self.address}:{self.port}"


# pylint: disable=too-many-instance-attributes
class IPServer(Adapter[Client]):
    """
    IP server stack adapter. The IP Adapter reads and writes bytes units (frames)

    Parameters
    ----------
    address : str
        IP address on which the server will listen
    port : int or None, default : None
        IP port on which the server will listen
    transport : {'TCP', 'UDP'}
        Transport layer
    stop_conditions : list[StopCondition] or StopCondition
        Stop coniditions are used to decide when a read data block is finished
        and should be returned

        These include

        * Termination : stop on a specific sequence like ``\\n`` at the end of the data
        * Length : stop when a specific number of bytes has been received
        * Continuation : stop when no data has been received for a
        specified amount of time
        * Total : stop if the time since the first piece of data received exceeds
        a given amount of time
        * FragmentStopCondition : Return each piece of data individually as received
        by the low-level communication layer

        Multiple stop conditions can be used to create more complex behaviours
    encoding : str
        Used to convert str to bytes if the user chooses to send str
    alias : str
        Name of the adapter, may be removed in the future
    event_callback : f(event : AdapterEvent)
        Function called when an event is received by the adapter worker thread.
        The event can be either one of :

        * ``AdapterOpenedEvent``
        * ``AdapterClosedEvent``
        * ``AdapterFrameEvent``
        * ``FirstFragmentEvent``
    auto_open : bool, default to True
        Automatically open the adapter after instanciation
    """

    DEFAULT_BACKLOG = 5

    def __init__(
        self,
        address: str,
        port: int | None = None,
        transport: str = IPDescriptor.Transport.TCP.value,
        stop_conditions: list[StopCondition] | StopCondition | EllipsisType = ...,
        *,
        backlog: int = DEFAULT_BACKLOG,
        alias: str = "",
        auto_open: bool = True,
    ):
        # pylint: disable=duplicate-code
        self._descriptor = IPDescriptor(
            address=address,
            port=port,
            transport=IPDescriptor.Transport(transport.upper()),
            server=True,
        )
        self._socket: socket.socket | None = None
        self._client_adapters: dict[str, IP] = {}
        self._backlog = backlog
        self._on_client_callbacks: list[Callable[[IP, AdapterEvent], None]] = []
        self._new_client_adapter_queue: queue.Queue[IP] = queue.Queue()
        # Attributes applied to each client
        if stop_conditions is ...:
            self._client_stop_conditions = IP._default_stop_conditions()
        elif isinstance(stop_conditions, StopCondition):
            self._client_stop_conditions = [stop_conditions]
        elif isinstance(stop_conditions, list):
            self._client_stop_conditions = stop_conditions
        else:
            raise ValueError("Invalid stop-conditions")

        super().__init__(
            worker=AdapterWorker(self),
            timeout=None,
            alias=alias,
            auto_open=auto_open
        )

        self.register_event_callback(self._on_event)

    def set_default_port(self, port: int) -> None:
        """
        Set the default port number

        Parameters
        ----------
        port : int
        """
        if self._descriptor.port is None:
            self._descriptor.port = port

    def _worker_read(self, fragment_timestamp: float) -> Fragment[Client]:
        if self._socket is None:
            raise AdapterReadError("Invalid socket")
        try:
            s, (address, port) = self._socket.accept()
        except (ConnectionRefusedError, OSError) as e:
            raise AdapterReadError(f"Read error : {str(e)}") from e

        fragment = Fragment(Client(address, port, s), fragment_timestamp)

        return fragment

    def _worker_write(self, data: Client) -> None:
        raise NotImplementedError()

    # pylint: disable=duplicate-code
    def _worker_open(self) -> None:
        # Create the socket instance
        if self._descriptor.transport == IPDescriptor.Transport.TCP:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif self._descriptor.transport == IPDescriptor.Transport.UDP:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        else:
            raise AdapterOpenError("Invalid transport protocol")
        try:
            self._socket.settimeout(self.timeout)
            self._socket.bind((self._descriptor.address, self._descriptor.port))
            self._socket.listen(self._backlog)
        except (OSError, ConnectionRefusedError, socket.gaierror) as e:
            msg = f"Failed to open server {self._descriptor} : {e}"
            self._logger.error(msg)
            raise AdapterOpenError(msg) from None

        self._logger.info(f"IPServer Adapter {self._descriptor} opened")

    # pylint: disable=duplicate-code
    def _worker_close(self) -> None:
        super()._worker_close()
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def write(self, data: Client) -> None:
        raise RuntimeError("Cannot write using IPServer, please use one of the clients")

    def _selectable(self) -> HasFileno | None:
        return self._socket

    @staticmethod
    def _default_stop_conditions() -> list[StopCondition]:
        return [Continuation(continuation=0.2)]

    @property
    def default_timeout(self) -> float | None:
        """Default timeout"""
        return 1.0

    def get_client(self, timeout: float | None = None) -> IP:
        """
        Return a new client

        Parameters
        ----------
        timeout : float or None
        """
        try:
            return self._new_client_adapter_queue.get(block=True, timeout=timeout)
        except queue.Empty:
            raise TimeoutError(
                "No client connected before the specified timeout"
            ) from None

    def register_client_callback(
        self, func: Callable[[IP, AdapterEvent], None]
    ) -> None:
        """Register the given function as a callback

        Function should have the form func(client : IP, event : AdapterEvent) -> None

        Parameters
        ----------
        func : Callable[[IP, AdapterEvent], None]
        """
        self._on_client_callbacks.append(func)

    @property
    def descriptor(self) -> IPDescriptor:
        return self._descriptor

    def _on_client_event(self, client: IP, event: AdapterEvent) -> None:
        for callback in self._on_client_callbacks:
            callback(client, event)

    def _on_event(self, event: AdapterEvent) -> None:
        if isinstance(event, AdapterFrameEvent):
            client = event.frame.data
            if isinstance(client, Client):
                client_adapter = IP(
                    address=client.address,
                    port=client.port,
                    transport=self._descriptor.transport,
                    server_socket=client.socket,
                    stop_conditions=self._client_stop_conditions,
                )
                client_adapter.register_event_callback(
                    lambda event: self._on_client_event(client_adapter, event)
                )
                self._client_adapters[client.address] = client_adapter
                self._new_client_adapter_queue.put(client_adapter)
