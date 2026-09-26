# File : protocol.py
# Author : Sébastien Deriaz
# License : GPL
"""
Protocols, the endpoints that turn the data of an adapter into payloads

A protocol always sits on an adapter and uses its engine, the non-blocking side of the
adapter where every method returns a future. What a protocol does to the data is written
once, in a Codec, and the ProtocolEngine applies it to the futures of the adapter
engine. Protocol and AsyncProtocol only wait for those futures, like Adapter and
AsyncAdapter
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Generic, Self, TypeVar

from syndesi.tools.errors import ProtocolError

from ..adapters.engine import AdapterEngine
from ..adapters.events import AdapterEvent
from ..adapters.framer import AdapterReadFrame, Frame
from ..adapters.utils import TimeoutParameterType, TimeoutType

ProtocolT = TypeVar("ProtocolT")
AdapterT = TypeVar("AdapterT")


@dataclass(kw_only=True)
class ProtocolReadFrame(Generic[ProtocolT], Frame[ProtocolT]):
    """A data unit received from a device, as returned to the user"""

    id: int
    response_delay: float

    def __str__(self) -> str:
        return f"ReadFrame({self.data})"


class ProtocolEngine(Generic[AdapterT, ProtocolT]):
    """
    Engine of a protocol : the futures of an adapter engine, carrying payloads

    Payloads are encoded before they are written, frames are decoded when a read
    completes. Frames nobody reads stay raw in the adapter buffer, so the adapter can
    still be used on its own

    Parameters
    ----------
    engine : Engine
        Engine of the adapter
    codec : Codec
    """

    def __init__(self, adapter_engine: AdapterEngine[Any, AdapterT]) -> None:
        self._adapter_engine = adapter_engine

    @property
    def is_open(self) -> bool:
        """True if the adapter is open"""
        return self._adapter_engine.is_open

    @property
    def timeout(self) -> TimeoutType:
        """Timeout of the adapter"""
        return self._adapter_engine.timeout

    def open(self) -> Future[None]:
        """Open the adapter"""
        return self._adapter_engine.open()

    def close(self) -> Future[None]:
        """Close the adapter"""
        return self._adapter_engine.close()

    def set_timeout(self, timeout: TimeoutType) -> Future[None]:
        """Set the timeout of the adapter"""
        return self._adapter_engine.set_timeout(timeout)

    def clear_buffer(self) -> Future[None]:
        """Drop the frames buffered by the adapter"""
        return self._adapter_engine.clear_buffer()

    def register_event_callback(
        self, callback: Callable[[AdapterEvent], None]
    ) -> Future[None]:
        """Register an adapter event callback"""
        return self._adapter_engine.register_event_callback(callback)

    def clear_event_callbacks(self) -> Future[None]:
        """Remove every adapter event callback"""
        return self._adapter_engine.clear_event_callbacks()

    def write(self, data: ProtocolT) -> Future[None]:
        """Encode a payload and write it"""
        try:
            encoded = self.encode(data)
        except ValueError as e:  # UnicodeError included
            raise ProtocolError(f"Cannot encode {data!r} : {e}") from e
        return self._adapter_engine.write(encoded)

    @abstractmethod
    def encode(self, payload: ProtocolT) -> AdapterT:
        """Turn a payload into the data written to the adapter"""

    @abstractmethod
    def decode(self, data: AdapterT) -> ProtocolT:
        """Turn the data of a frame read from the adapter into a payload"""

    def read_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        # scope: ReadScope = ReadScope.BUFFERED,
        # stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
    ) -> Future[ProtocolReadFrame[ProtocolT]]:
        """Read one frame and decode it"""

        source = self._adapter_engine.read(timeout)  # , scope, stop_conditions)

        output: Future[ProtocolReadFrame[ProtocolT]] = Future()

        def on_output_done(future: Future[ProtocolReadFrame[ProtocolT]]) -> None:
            if future.cancelled():
                source.cancel()

        def on_source_done(future: Future[AdapterReadFrame[AdapterT]]) -> None:
            if future.cancelled():
                output.cancel()
                return
            if not output.set_running_or_notify_cancel():
                return
            error = future.exception()
            if error is not None:
                output.set_exception(error)
                return
            try:
                adapter_frame = future.result()
                protocol_frame = ProtocolReadFrame(
                    data=self.decode(adapter_frame.data),
                    id=adapter_frame.id,
                    response_delay=adapter_frame.response_delay,
                )
                output.set_result(protocol_frame)
            except Exception as e:  # pylint: disable=broad-exception-caught
                output.set_exception(e)

        output.add_done_callback(on_output_done)
        source.add_done_callback(on_source_done)
        return output

ProtocolEngineT = TypeVar("ProtocolEngineT", bound=ProtocolEngine[Any, Any])

class ProtocolCommon(Generic[ProtocolEngineT]):
    """
    Common class for Protocol and AsyncProtocol
    """

    def __init__(self, engine: ProtocolEngineT) -> None:
        self._engine = engine

class Protocol(
    Generic[ProtocolEngineT, AdapterT, ProtocolT], ProtocolCommon[ProtocolEngineT]
):
    """
    Sync protocol

    Parameters
    ----------
    adapter : Adapter
    codec : Codec
    timeout : float, None or ...
        ``...`` keeps the adapter timeout if it was given one, the codec one otherwise
    """

    def __str__(self) -> str:
        return f"{type(self).__name__}()"

    def __repr__(self) -> str:
        return self.__str__()

    def open(self) -> None:
        """Open communication with the target"""
        self._engine.open().result()

    def close(self) -> None:
        """Close communication with the target"""
        self._engine.close().result()

    def write(self, data: ProtocolT) -> None:
        """Write data to the target"""
        self._engine.write(data).result()

    def read_detailed(
        self, timeout: TimeoutParameterType = ...
    ) -> ProtocolReadFrame[ProtocolT]:
        """Read one frame"""
        return self._engine.read_detailed(timeout=timeout).result()

    def read(self, timeout: TimeoutParameterType = ...) -> ProtocolT:
        """Read one frame and return its data"""
        return self.read_detailed(timeout=timeout).data

    def query_detailed(
        self, payload: ProtocolT, timeout: TimeoutParameterType = ...
    ) -> ProtocolReadFrame[ProtocolT]:
        self.write(payload)
        return self.read_detailed(timeout=timeout)

    def query(self, payload: ProtocolT, timeout: TimeoutParameterType) -> ProtocolT:
        return self.query_detailed(payload=payload, timeout=timeout).data

    def __enter__(self) -> Self:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

class AsyncProtocol(
    Generic[ProtocolEngineT, AdapterT, ProtocolT], ProtocolCommon[ProtocolEngineT]
):
    """
    Async protocol, same parameters as Protocol

    The adapter configuration is submitted without waiting, it applies before any
    later operation
    """

    def __str__(self) -> str:
        return f"{type(self).__name__}()"

    def __repr__(self) -> str:
        return self.__str__()

    async def open(self) -> None:
        """Open communication with the target"""
        await asyncio.wrap_future(self._engine.open())

    async def close(self) -> None:
        """Close communication with the target"""
        await asyncio.wrap_future(self._engine.close())

    async def write(self, data: ProtocolT) -> None:
        await asyncio.wrap_future(self._engine.write(data))

    async def read_detailed(
        self, timeout: TimeoutParameterType = ...
    ) -> ProtocolReadFrame[ProtocolT]:
        return await asyncio.wrap_future(self._engine.read_detailed(timeout=timeout))

    async def read(self, timeout: TimeoutParameterType = ...) -> ProtocolT:
        """Read one frame and return its data"""
        frame = await self.read_detailed(timeout=timeout)
        return frame.data

    async def query_detailed(
        self, payload: ProtocolT, timeout: TimeoutParameterType = ...
    ) -> ProtocolReadFrame[ProtocolT]:
        await self.write(payload)
        return await self.read_detailed(timeout=timeout)

    async def query(
        self, payload: ProtocolT, timeout: TimeoutParameterType
    ) -> ProtocolT:
        frame = await self.query_detailed(payload=payload, timeout=timeout)
        return frame.data

    async def __aenter__(self) -> Self:
        await self.open()
        return self

    async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
    ) -> None:
        await self.close()
