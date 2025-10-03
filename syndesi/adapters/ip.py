# File : ip.py
# Author : Sébastien Deriaz
# License : GPL
#
# IP adapter, communicates with TCP or UDP


from collections.abc import Callable
from types import EllipsisType

from syndesi.adapters.backend.adapter_backend import AdapterSignal
from syndesi.tools.types import NumberLike

from .adapter import Adapter
from .backend.descriptors import IPDescriptor
from .stop_condition import StopCondition
from .timeout import Timeout

# TODO : Server ? create an adapter from a socket ?

# TODO : Manage opening and closing, modes ? open at instance or at write/read ? close after read ? error if already opened before / strict mode ?


class IP(Adapter):
    DEFAULT_PROTOCOL = IPDescriptor.Transport.TCP

    def __init__(
        self,
        address: str,
        port: int | None = None,
        transport: str = DEFAULT_PROTOCOL.value,
        timeout: Timeout | NumberLike | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        alias: str = "",
        encoding: str = "utf-8",
        event_callback: Callable[[AdapterSignal], None] | None = None,
        auto_open: bool = True,
        backend_address: str | None = None,
        backend_port: int | None = None,
    ):
        """
        IP adapter

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
        auto_open : bool
            Automatically open the adapter
        socket : socket.socket
            Specify a custom socket, this is reserved for server application

        """
        super().__init__(
            descriptor=IPDescriptor(
                address=address,
                port=port,
                transport=IPDescriptor.Transport(transport.upper()),
            ),
            alias=alias,
            timeout=timeout,
            stop_conditions=stop_conditions,
            encoding=encoding,
            event_callback=event_callback,
            auto_open=auto_open,
            backend_address=backend_address,
            backend_port=backend_port,
        )
        self.descriptor: IPDescriptor

        # if self.descriptor.transport is not None:
        self._logger.info(f"Setting up {self.descriptor.transport.value} IP adapter")

        self.set_default_timeout(self._default_timeout())

    def _default_timeout(self) -> Timeout:
        return Timeout(response=5, action="error")

    def set_default_port(self, port: int) -> None:
        """
        Sets IP port if no port has been set yet.

        This way, the user can leave the port empty
        and the driver/protocol can specify it later

        Parameters
        ----------
        port : int
        """
        if self.descriptor.port is None:
            self.descriptor.port = port

    def set_default_transport(self, transport: str | IPDescriptor.Transport) -> None:
        """
        Sets the default IP transport protocol

        Parameters
        ----------
        transport : str | IPDescriptor.Transport
        """
        if self.descriptor.transport is None:
            self.descriptor.transport = IPDescriptor.Transport(transport)
