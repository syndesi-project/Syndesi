# File : raw.py
# Author : Sébastien Deriaz
# License : GPL

from collections.abc import Callable
from types import EllipsisType

from syndesi.adapters.backend.adapter_backend import AdapterReadPayload, AdapterSignal
from syndesi.adapters.stop_condition import StopCondition

from ..adapters.adapter import Adapter
from ..adapters.timeout import Timeout
from .protocol import Protocol

# Raw protocols provide the user with the binary data directly,
# without converting it to string first


class Raw(Protocol):
    def __init__(
        self,
        adapter: Adapter,
        timeout: Timeout | None | EllipsisType = ...,
        event_callback: Callable[[AdapterSignal], None] | None = None,
    ) -> None:
        """
        Raw device, no presentation and application layers

        Parameters
        ----------
        adapter : IAdapter
        """
        super().__init__(
            adapter,
            timeout,
            event_callback,
        )

        # Connect the adapter if it wasn't done already
        self._adapter.connect()

    def _default_timeout(self) -> Timeout | None:
        return Timeout(response=2, action="error")

    def write(self, data: bytes) -> None:
        self._adapter.write(data)

    def query(
        self,
        data: bytes,
        timeout: Timeout | None | EllipsisType = ...,
        stop_condition: StopCondition | None | EllipsisType = ...,
        full_output: bool = False,
    ) -> bytes | tuple[bytes, AdapterSignal]:
        self._adapter.flushRead()
        self.write(data)
        return self.read(
            timeout=timeout,
            stop_condition=stop_condition,
            full_output=full_output,
        )

    def read(
        self,
        timeout: Timeout | None | EllipsisType = ...,
        stop_condition: StopCondition | None | EllipsisType = ...,
        full_output: bool = False,
    ) -> bytes | tuple[bytes, AdapterSignal]:

        return self.read_detailed(timeout=timeout, stop_condition=stop_condition)[0]

    def read_detailed(
        self,
        timeout: Timeout | None | EllipsisType = ...,
        stop_condition: StopCondition | None | EllipsisType = ...,
    ) -> tuple[bytes, AdapterSignal | None]:
        return self._adapter.read_detailed(
            timeout=timeout, stop_condition=stop_condition
        )

    def _on_data_ready_event(self, data: AdapterReadPayload) -> None:
        # TODO : Call the callback here ?
        pass

    def __str__(self) -> str:
        return f"Raw({self._adapter})"
