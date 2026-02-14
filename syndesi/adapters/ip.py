# File : ip.py
# Author : Sébastien Deriaz
# License : GPL
"""
IP Adapter, used to communicate with IP targets using the socket module
"""

import socket
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from types import EllipsisType

from syndesi.adapters.adapter_worker import AdapterEvent, AdapterFrameEvent, HasFileno
from syndesi.adapters.stop_conditions import Continuation, StopCondition
from syndesi.adapters.timeout import Timeout
from syndesi.component import Descriptor
from syndesi.tools.errors import AdapterOpenError, AdapterWriteError

from .adapter import Adapter
from .stop_conditions import Fragment


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

    DETECTION_PATTERN = r"(\d+.\d+.\d+.\d+|[\w\.]+):\d+:(UDP|TCP)"
    address: str
    transport: Transport
    port: int | None = None

    @staticmethod
    def from_string(string: str) -> "IPDescriptor":
        parts = string.split(":")
        address = parts[0]
        port = int(parts[1])
        transport = IPDescriptor.Transport(parts[2])
        return IPDescriptor(address, transport, port)

    def __str__(self) -> str:
        return f"{self.address}:{self.port}:{self.Transport(self.transport).value}"

    def is_initialized(self) -> bool:
        """
        Return True if all attributes has been defined (not None)
        """

        return self.port is not None and self.transport is not None

BUFFER_SIZE = 65535

class IP(Adapter[bytes]):
    """
    IP stack adapter. The IP Adapter reads and writes bytes units (frames)

    Parameters
    ----------
    address : str
        IP address
    port : int or None, default : None
        IP port
    transport : {'TCP', 'UDP'}
        Transport layer
    timeout : Timeout or float
        Specify communication timeout, the time it takes for the target to respond
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

        * ``AdapterDisconnectedEvent``
        * ``AdapterFrameEvent``
        * ``FirstFragmentEvent``
    auto_open : bool, default to True
        Automatically open the adapter after instanciation
    """
    def __init__(
        self,
        address: str,
        port: int | None = None,
        transport: str = IPDescriptor.Transport.TCP.value,
        server : bool = False,
        *,
        timeout: Timeout | float | EllipsisType = ...,
        stop_conditions: list[StopCondition] | StopCondition | EllipsisType = ...,
        encoding: str = "utf-8",
        alias: str = "",
        event_callback: Callable[[AdapterEvent], None] | None = None,
        auto_open: bool = True,
    ):

        descriptor = IPDescriptor(
            address=address,
            port=port,
            transport=IPDescriptor.Transport(transport.upper()),
        )
        #self._socket: _socket.socket | None = None
        self._socket : socket.socket | None = None

        super().__init__(
            descriptor=descriptor,
            stop_conditions=stop_conditions,
            timeout=timeout,
            encoding=encoding,
            alias=alias,
            event_callback=event_callback,
            auto_open=auto_open,
        )
        self._descriptor: IPDescriptor
        self._worker_descriptor: IPDescriptor

    def set_default_port(self, port: int) -> None:
        """
        Set the default port number

        Parameters
        ----------
        port : int
        """
        if self._descriptor.port is None:
            self._descriptor.port = port
            self._update_descriptor()

    def _worker_read(self, fragment_timestamp: float) -> Fragment:
        if self._socket is None:
            return Fragment(b"", fragment_timestamp)

        try:
            data = self._socket.recv(BUFFER_SIZE)
        except (ConnectionRefusedError, OSError):
            fragment = Fragment(b"", fragment_timestamp)
        else:
            if data == b"":
                #self._logger.warning("Socket disconnected")
                self._worker_close()
            fragment = Fragment(data, fragment_timestamp)
        return fragment

    def _worker_write(self, data: bytes) -> None:
        super()._worker_write(data)

        if self._socket is not None:
            if self._socket.send(data) != len(data):
                raise AdapterWriteError(
                    f"Adapter {self._worker_descriptor} couldn't write"
                    " all of the data to the socket"
                )

    def _worker_open(self) -> None:
        super()._worker_open()
        self._worker_check_descriptor()

        # Create the socket instance
        if self._worker_descriptor.transport == IPDescriptor.Transport.TCP:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif self._worker_descriptor.transport == IPDescriptor.Transport.UDP:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        else:
            raise AdapterOpenError("Invalid transport protocol")
        try:
            self._socket.settimeout(self.WorkerTimeout.OPEN.value)
            self._socket.connect(
                (self._worker_descriptor.address, self._worker_descriptor.port)
            )
        except (OSError, ConnectionRefusedError, socket.gaierror) as e:
            self._opened = False
            msg = f"Failed to open adapter {self._worker_descriptor} : {e}"
            self._logger.error(msg)
            raise AdapterOpenError(msg) from None

        self._opened = True
        self._logger.info(f"IP Adapter {self._worker_descriptor} opened")

    def _worker_close(self) -> None:
        super()._worker_close()
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _selectable(self) -> HasFileno | None:
        return self._socket

    def _default_stop_conditions(self) -> list[StopCondition]:
        return [Continuation(continuation=0.2)]

    def _default_timeout(self) -> Timeout:
        return Timeout(response=1, action="error")


@dataclass
class ClientFragment:
    """Data packet received or sent to an IPServer client"""
    address : str
    socket : socket.socket

class IPServer(Adapter[ClientFragment]):
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

        * ``AdapterDisconnectedEvent``
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
        *,
        backlog : int = DEFAULT_BACKLOG,
        stop_conditions: list[StopCondition] | StopCondition | EllipsisType = ...,
        encoding: str = "utf-8",
        alias: str = "",
        event_callback: Callable[[AdapterEvent], None] | None = None,
        auto_open : bool = True
    ):

        descriptor = IPDescriptor(
            address=address,
            port=port,
            transport=IPDescriptor.Transport(transport.upper()),
        )
        self._socket : socket.socket | None = None

        self._descriptor: IPDescriptor
        self._worker_descriptor: IPDescriptor

        self._backlog = backlog
        
        super().__init__(
            descriptor=descriptor,
            stop_conditions=stop_conditions,
            timeout=None,
            encoding=encoding,
            alias=alias,
            event_callback=event_callback,
            auto_open=auto_open,
        )

        self.set_event_callback(self._on_event)

    def set_default_port(self, port: int) -> None:
        """
        Set the default port number

        Parameters
        ----------
        port : int
        """
        if self._descriptor.port is None:
            self._descriptor.port = port
            self._update_descriptor()

    def _worker_read(self, fragment_timestamp: float) -> Fragment[ClientFragment]:
        print(f'IP server read')
        if self._socket is None:
            print(f'Socket None')
            return Fragment(b"", fragment_timestamp)
        try:
            socket, address = self._socket.accept()
        except (ConnectionRefusedError, OSError):
            print('Connection refused error')
            fragment = Fragment(b"", fragment_timestamp)
        else:
            
            fragment = Fragment(ClientFragment(address, socket), fragment_timestamp)
            # if data == b"":
            #     print('Empty data')
            #     self._logger.warning("Socket disconnected")
            #     self._worker_close()
            #fragment = Fragment(data, fragment_timestamp)
        return fragment
    
# Idea : The IPServer creates IP clients (instance of IP with the specific client address/port). The server would provide helper function to manage all of that.

    def _worker_write(self, data: bytes) -> None:
        raise NotImplementedError()

    def _worker_open(self) -> None:
        super()._worker_open()
        self._worker_check_descriptor()

        # Create the socket instance
        if self._worker_descriptor.transport == IPDescriptor.Transport.TCP:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        elif self._worker_descriptor.transport == IPDescriptor.Transport.UDP:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        else:
            raise AdapterOpenError("Invalid transport protocol")
        try:
            self._socket.settimeout(self.WorkerTimeout.OPEN.value)
            self._socket.bind(
                (self._worker_descriptor.address, self._worker_descriptor.port)
            )
            self._socket.listen(self._backlog)
        except (OSError, ConnectionRefusedError, socket.gaierror) as e:
            self._opened = False
            msg = f"Failed to open adapter {self._worker_descriptor} : {e}"
            self._logger.error(msg)
            raise AdapterOpenError(msg) from None

        self._opened = True
        self._logger.info(f"IP Adapter {self._worker_descriptor} opened")

    def _worker_close(self) -> None:
        super()._worker_close()
        if self._socket is not None:
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def write(self, data: bytes | str) -> None:
        raise RuntimeError("Cannot write using IPServer, please use one of the clients")

    def _selectable(self) -> HasFileno | None:
        return self._socket

    def _default_stop_conditions(self) -> list[StopCondition]:
        return [Continuation(continuation=0.2)]

    def _default_timeout(self) -> Timeout:
        return Timeout(response=1, action="error")
    
    def _on_event(self, event : AdapterEvent):
        print(f'IP Server event : {event}')
        if isinstance(event, AdapterFrameEvent):
            ...
            


