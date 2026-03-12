# File : raw.py
# Author : Sébastien Deriaz
# License : GPL
"""
Raw protocol layer, data is returned as bytes "as-is"
"""

from collections.abc import Callable
from types import EllipsisType

from ..adapters.adapterbase import AdapterBase
from ..adapters.timeout import Timeout
from ..component import Frame
from .protocol import Protocol, ProtocolEvent, ProtocolFrame


class Raw(Protocol[bytes, bytes]):
    """
    Raw device, no presentation and application layers, data is returned as bytes directly

    Parameters
    ----------
    adapter : IAdapter
    """

    def __init__(
        self,
        adapter: AdapterBase[bytes],
        timeout: Timeout | None | EllipsisType = ...,
        event_callback: Callable[[ProtocolEvent], None] | None = None,
    ) -> None:
        super().__init__(adapter, timeout, event_callback)

    def _default_timeout(self) -> Timeout | None:
        return Timeout(response=2)

    def __str__(self) -> str:
        return f"Raw({self._adapter})"

    # def _on_event(self, event: AdapterEvent) -> None:
    #     if self._event_callback is not None:
    #         output_event: ProtocolEvent | None = None
    #         if isinstance(event, AdapterDisconnectedEvent):
    #             output_event = ProtocolDisconnectedEvent()
    #         if isinstance(event, AdapterFrameEvent):
    #             output_event = ProtocolFrameEvent(
    #                 frame=self._adapter_to_protocol(event.frame)
    #             )

    #         if output_event is not None:
    #             self._event_callback(output_event)

    def _adapter_to_protocol(self, adapter_frame: Frame[bytes]) -> ProtocolFrame[bytes]:
        payload = adapter_frame.data

        return ProtocolFrame(
            data=payload,
            stop_timestamp=adapter_frame.stop_timestamp,
            stop_condition_type=adapter_frame.stop_condition_type,
            previous_read_buffer_used=adapter_frame.previous_read_buffer_used,
            response_delay=adapter_frame.response_delay,
        )

    def _protocol_to_adapter(self, protocol_payload: bytes) -> bytes:
        return protocol_payload
