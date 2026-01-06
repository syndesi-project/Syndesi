# File : raw.py
# Author : Sébastien Deriaz
# License : GPL
"""
Raw protocol layer, data is returned as bytes "as-is"
"""

from collections.abc import Callable
from dataclasses import dataclass
from types import EllipsisType

from ..adapters.adapter import Adapter
from ..adapters.adapter_worker import AdapterEvent
from ..adapters.timeout import Timeout
from ..component import AdapterFrame
from .protocol import Protocol, ProtocolEvent, ProtocolFrame

# Raw protocols provide the user with the binary data directly,
# without converting it to string first


@dataclass
class RawFrame(ProtocolFrame[bytes]):
    """
    Adapter signal containing received data
    """

    payload: bytes

    def __str__(self) -> str:
        return f"ProtocolFrame({self.payload!r})"


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
        event_callback: Callable[[ProtocolEvent], None] | None = None,
    ) -> None:
        super().__init__(adapter, timeout)

    def _default_timeout(self) -> Timeout | None:
        return Timeout(response=2, action="error")

    def __str__(self) -> str:
        return f"Raw({self._adapter})"

    def _on_event(self, event: AdapterEvent) -> None:
        ...
        # TODO : implement

    def _adapter_to_protocol(self, adapter_frame: AdapterFrame) -> RawFrame:
        payload = adapter_frame.get_payload()

        return RawFrame(
            payload=payload,
            stop_timestamp=adapter_frame.stop_timestamp,
            stop_condition_type=adapter_frame.stop_condition_type,
            previous_read_buffer_used=adapter_frame.previous_read_buffer_used,
            response_delay=adapter_frame.response_delay,
        )

    def _protocol_to_adapter(self, protocol_payload: bytes) -> bytes:
        return protocol_payload
