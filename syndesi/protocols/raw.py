# File : raw.py
# Author : Sébastien Deriaz
# License : GPL
"""
Raw protocol layer, data is returned as bytes "as-is"
"""

from collections.abc import Callable
from types import EllipsisType

from syndesi.adapters.backend.adapter_backend import AdapterReadPayload, AdapterSignal
from syndesi.adapters.stop_condition import StopCondition

from ..adapters.adapter import Adapter
from ..adapters.timeout import Timeout
from .protocol import Protocol

# Raw protocols provide the user with the binary data directly,
# without converting it to string first


class Raw(Protocol[bytes]):
    """
    Raw device, no presentation and application layers, data is returned as bytes directly

    Parameters
    ----------
    adapter : IAdapter
    """
    def __init__(
        self,
        adapter: Adapter,
        timeout: Timeout | None | EllipsisType = ...,
        event_callback: Callable[[AdapterSignal], None] | None = None,
    ) -> None:
        super().__init__(
            adapter,
            timeout,
            event_callback,
        )

        # Connect the adapter if it wasn't done already
        self._adapter.connect()

    def _default_timeout(self) -> Timeout | None:
        return Timeout(response=2, action="error")

    def write(self, payload: bytes) -> None:
        self._adapter.write(payload)

    def read(
        self,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> bytes:
        """
        Blocking read and return bytes data

        Parameters
        ----------
        timeout : Timeout
            Optional temporary timeout
        stop_conditions : [StopCondition]
            Optional temporary stop-conditions

        Returns
        -------
        data : bytes
        """
        signal = self.read_detailed(timeout=timeout, stop_conditions=stop_conditions)
        return signal.data()

    def _on_data_ready_event(self, data: AdapterReadPayload) -> None:
        # TODO : Call the callback here ?
        pass

    def __str__(self) -> str:
        return f"Raw({self._adapter})"
