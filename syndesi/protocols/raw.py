# NOT YET PORTED to the backend/framer/engine/reactor architecture.
# This module still targets the removed Component/Adapter classes. It is kept
# as a reference while it gets ported, and excluded from the checkers until then
# mypy: ignore-errors
# pylint: skip-file
# ruff: noqa
# File : raw.py
# Author : Sébastien Deriaz
# License : GPL
"""
Raw protocol layer, data is returned as bytes "as-is"
"""

from syndesi.adapters.utils import TimeoutParameterType

from .protocol import AsyncProtocol, Protocol
from ..adapters.bytesadapter import BytesAdapter
from ..component import ReadFrame
from .protocol import ProtocolReadFrame

class Raw(Protocol[bytes]):
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
        timeout: TimeoutParameterType = ...
    ) -> None:
        super().__init__(adapter, timeout)

    @property
    def default_timeout(self) -> float | None:
        """Default timeout"""
        return 2.0

    def __str__(self) -> str:
        return f"Raw({self.adapter})"

    def _adapter_to_protocol(self, adapter_frame: ReadFrame[bytes]) -> ProtocolReadFrame[bytes]:
        payload = adapter_frame.data

        return ProtocolReadFrame(
            data=payload,
            id=adapter_frame.id,
            stop_timestamp=adapter_frame.stop_timestamp,
            stop_condition=adapter_frame.stop_condition,
            previous_read_buffer_used=adapter_frame.previous_read_buffer_used,
            response_delay=adapter_frame.response_delay,
        )

    def _protocol_to_adapter(self, protocol_payload: bytes) -> bytes:
        return protocol_payload

class AsyncRaw(AsyncProtocol[bytes]):
    """
    Raw device, no presentation and application layers, data is returned as bytes directly

    Parameters
    ----------
    adapter : Adapter
    timeout : float | int | None | ...
    """
    ...