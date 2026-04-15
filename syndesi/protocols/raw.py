# File : raw.py
# Author : Sébastien Deriaz
# License : GPL
"""
Raw protocol layer, data is returned as bytes "as-is"
"""

from types import EllipsisType

from syndesi.adapters.utils import TimeoutType

from ..adapters.bytesadapter import BytesAdapter
from ..component import Frame
from .protocol import Protocol, ProtocolFrame


class Raw(Protocol[bytes, bytes]):
    """
    Raw device, no presentation and application layers, data is returned as bytes directly

    Parameters
    ----------
    adapter : Adapter
    timeout : float | int | None | ...
    """

    def __init__(
        self,
        adapter: BytesAdapter,
        timeout: TimeoutType = ...
    ) -> None:
        super().__init__(adapter, timeout)

    @staticmethod
    def default_timeout() -> float | None:
        """Default timeout"""
        return 2.0

    def __str__(self) -> str:
        return f"Raw({self._adapter})"

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
