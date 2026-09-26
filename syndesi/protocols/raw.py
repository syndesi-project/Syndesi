# File : raw.py
# Author : Sébastien Deriaz
# License : GPL
"""
Raw protocol, the frames of the adapter are returned as bytes as-is
"""

from __future__ import annotations

from typing import Any

from ..adapters.adapter import Adapter, AsyncAdapter
from ..adapters.framer import AdapterReadFrame
from ..adapters.utils import TimeoutParameterType, TimeoutType
from .protocol import AsyncProtocol, BackendOutput, Protocol, ProtocolBackend


class RawBackend(ProtocolBackend[bytes, bytes]):
    """
    No encoding and no assembly, one adapter frame is one payload

    Leaves the adapter stop-conditions alone : with Raw, the framing the user gave the
    adapter is the whole point
    """

    def encode(self, payload: bytes) -> list[bytes]:
        return [payload]

    def push(self, frame: AdapterReadFrame[bytes]) -> BackendOutput[bytes, bytes]:
        return BackendOutput(payloads=[frame.data])

    @property
    def default_timeout(self) -> TimeoutType:
        return 2.0


class Raw(Protocol[RawBackend, bytes, bytes]):
    """
    Raw protocol, no presentation and no application layer

    Parameters
    ----------
    adapter : Adapter
    timeout : float, None or ...
        Time to wait for a frame, 2 s by default
    alias : str
    """

    def __init__(
        self,
        adapter: Adapter[Any, bytes],
        timeout: TimeoutParameterType = ...,
        alias: str = "",
    ) -> None:
        super().__init__(adapter, RawBackend(), timeout, alias)


class AsyncRaw(AsyncProtocol[RawBackend, bytes, bytes]):
    """
    Async raw protocol, same parameters as Raw
    """

    def __init__(
        self,
        adapter: AsyncAdapter[Any, bytes],
        timeout: TimeoutParameterType = ...,
        alias: str = "",
    ) -> None:
        super().__init__(adapter, RawBackend(), timeout, alias)
