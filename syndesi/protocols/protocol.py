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

    Delimited ──contains──▶ ProtocolEngine ──uses──▶ Engine ◀──contains── IP
                              └ DelimitedCodec
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import Future
from types import EllipsisType
from typing import Any, Generic, TypeVar, cast

from ..adapters.adapter import Adapter, AsyncAdapter
from ..adapters.engine import Engine, ReadScope
from ..adapters.events import AdapterEvent
from ..adapters.framer import ReadFrame
from ..adapters.stop_conditions import StopCondition
from ..adapters.utils import TimeoutParameterType, TimeoutType
from ..endpoint import AsyncEndpoint, Endpoint
from ..tools.errors import ProtocolReadError, ProtocolWriteError

WireT = TypeVar("WireT")
PayloadT = TypeVar("PayloadT")
SourceT = TypeVar("SourceT")
ResultT = TypeVar("ResultT")


class Codec(ABC, Generic[WireT, PayloadT]):
    """
    Translation between the data of an adapter and the payloads of a protocol, no I/O

    A codec is immutable : changing it means handing a new one to the protocol, so a
    decode running on the reactor thread always sees a consistent codec
    """

    @property
    @abstractmethod
    def default_timeout(self) -> TimeoutType:
        """Timeout used when neither the protocol nor the adapter was given one"""

    @property
    @abstractmethod
    def stop_conditions(self) -> list[StopCondition] | None:
        """Stop-conditions given to the adapter, None to keep the adapter ones"""

    @abstractmethod
    def encode(self, payload: PayloadT) -> WireT:
        """Turn a payload into the data written to the adapter"""

    @abstractmethod
    def decode(self, data: WireT) -> PayloadT:
        """Turn the data of a frame read from the adapter into a payload"""


def _chain(source: Future[SourceT], convert: Callable[[SourceT], ResultT]) -> Future[ResultT]:
    """
    Return a future completed with convert() applied to the result of source

    convert runs on the thread completing source, the reactor. Cancelling the returned
    future cancels source, so the engine frees its read slot
    """
    output: Future[ResultT] = Future()

    def on_output_done(future: Future[ResultT]) -> None:
        if future.cancelled():
            source.cancel()

    def on_source_done(future: Future[SourceT]) -> None:
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
            output.set_result(convert(future.result()))
        except Exception as e:  # pylint: disable=broad-exception-caught
            output.set_exception(e)

    output.add_done_callback(on_output_done)
    source.add_done_callback(on_source_done)
    return output


class ProtocolEngine(Generic[WireT, PayloadT]):
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

    def __init__(self, engine: Engine[Any, WireT], codec: Codec[WireT, PayloadT]) -> None:
        self._engine = engine
        self._codec = codec

    @property
    def codec(self) -> Codec[WireT, PayloadT]:
        """Codec of the protocol"""
        return self._codec

    @property
    def is_open(self) -> bool:
        """True if the adapter is open"""
        return self._engine.is_open

    @property
    def timeout(self) -> TimeoutType:
        """Timeout of the adapter"""
        return self._engine.timeout

    def open(self) -> Future[None]:
        """Open the adapter"""
        return self._engine.open()

    def close(self) -> Future[None]:
        """Close the adapter"""
        return self._engine.close()

    def set_timeout(self, timeout: TimeoutType) -> Future[None]:
        """Set the timeout of the adapter"""
        return self._engine.set_timeout(timeout)

    def clear_buffer(self) -> Future[None]:
        """Drop the frames buffered by the adapter"""
        return self._engine.clear_buffer()

    def register_event_callback(self, callback: Callable[[AdapterEvent], None]) -> Future[None]:
        """Register an adapter event callback"""
        return self._engine.register_event_callback(callback)

    def clear_event_callbacks(self) -> Future[None]:
        """Remove every adapter event callback"""
        return self._engine.clear_event_callbacks()

    def write(self, data: PayloadT) -> Future[None]:
        """Encode a payload and write it"""
        try:
            encoded = self._codec.encode(data)
        except ValueError as e:  # UnicodeError included
            raise ProtocolWriteError(f"Cannot encode {data!r} : {e}") from e
        return self._engine.write(encoded)

    def read(
        self,
        timeout: TimeoutParameterType = ...,
        scope: ReadScope = ReadScope.BUFFERED,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
    ) -> Future[ReadFrame[PayloadT]]:
        """Read one frame and decode it"""
        return _chain(self._engine.read(timeout, scope, stop_conditions), self._decode)

    def set_codec(self, codec: Codec[WireT, PayloadT]) -> Future[None]:
        """Use another codec, its stop-conditions go to the adapter"""
        self._codec = codec
        stop_conditions = codec.stop_conditions
        if stop_conditions is None:
            done: Future[None] = Future()
            done.set_result(None)
            return done
        return self._engine.set_stop_conditions(stop_conditions)

    def _decode(self, frame: ReadFrame[WireT]) -> ReadFrame[PayloadT]:
        try:
            data = self._codec.decode(frame.data)
        except ValueError as e:  # UnicodeError included
            raise ProtocolReadError(f"Cannot decode {frame.data!r} : {e}") from e
        return ReadFrame(
            data=data,
            id=frame.id,
            stop_timestamp=frame.stop_timestamp,
            stop_condition=frame.stop_condition,
            first_fragment_timestamp=frame.first_fragment_timestamp,
            response_delay=frame.response_delay,
        )


def _build_engine(
    adapter: Adapter[Any, WireT] | AsyncAdapter[Any, WireT],
    codec: Codec[WireT, PayloadT],
    timeout: TimeoutParameterType,
) -> tuple[ProtocolEngine[WireT, PayloadT], list[Future[None]]]:
    """
    Build the engine of a protocol and configure its adapter

    The codec stop-conditions replace the adapter ones. ``...`` keeps the adapter
    timeout if it was given one, and uses the codec one otherwise

    The configuration is submitted to the adapter engine and returned without waiting :
    the engine runs commands in order, so it applies before any later operation
    """
    engine = adapter.engine
    configuration: list[Future[None]] = []

    stop_conditions = codec.stop_conditions
    if stop_conditions is not None:
        configuration.append(engine.set_stop_conditions(stop_conditions))

    if timeout is not ...:
        configuration.append(engine.set_timeout(timeout))
    elif adapter.has_default_timeout:
        configuration.append(engine.set_timeout(codec.default_timeout))

    return ProtocolEngine(engine, codec), configuration


class Protocol(Endpoint[PayloadT], Generic[WireT, PayloadT]):
    """
    Sync protocol

    Parameters
    ----------
    adapter : Adapter
    codec : Codec
    timeout : float, None or ...
        ``...`` keeps the adapter timeout if it was given one, the codec one otherwise
    """

    def __init__(
        self,
        adapter: Adapter[Any, WireT],
        codec: Codec[WireT, PayloadT],
        *,
        timeout: TimeoutParameterType = ...,
    ) -> None:
        # Public, the UI uses it
        self.adapter = adapter
        engine, configuration = _build_engine(adapter, codec, timeout)
        # Waited for, so that the adapter attributes (timeout, ...) are up to date
        for future in configuration:
            future.result()
        super().__init__(engine, auto_open=False)

    def __str__(self) -> str:
        return f"{type(self).__name__}({self.adapter},{self.codec})"

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def codec(self) -> Codec[WireT, PayloadT]:
        """Codec of the protocol"""
        return self._protocol_engine.codec

    def _set_codec(self, codec: Codec[WireT, PayloadT]) -> None:
        self._protocol_engine.set_codec(codec).result()

    @property
    def _protocol_engine(self) -> ProtocolEngine[WireT, PayloadT]:
        return cast("ProtocolEngine[WireT, PayloadT]", self._engine)


class AsyncProtocol(AsyncEndpoint[PayloadT], Generic[WireT, PayloadT]):
    """
    Async protocol, same parameters as Protocol

    The adapter configuration is submitted without waiting, it applies before any
    later operation
    """

    def __init__(
        self,
        adapter: AsyncAdapter[Any, WireT],
        codec: Codec[WireT, PayloadT],
        *,
        timeout: TimeoutParameterType = ...,
    ) -> None:
        # Public, the UI uses it
        self.adapter = adapter
        engine, _ = _build_engine(adapter, codec, timeout)
        super().__init__(engine, auto_open=False)

    def __str__(self) -> str:
        return f"{type(self).__name__}({self.adapter},{self.codec})"

    def __repr__(self) -> str:
        return self.__str__()

    @property
    def codec(self) -> Codec[WireT, PayloadT]:
        """Codec of the protocol"""
        return self._protocol_engine.codec

    async def _set_codec(self, codec: Codec[WireT, PayloadT]) -> None:
        await asyncio.wrap_future(self._protocol_engine.set_codec(codec))

    @property
    def _protocol_engine(self) -> ProtocolEngine[WireT, PayloadT]:
        return cast("ProtocolEngine[WireT, PayloadT]", self._engine)
