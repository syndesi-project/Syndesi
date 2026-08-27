# File : protocol.py
# Author : Sébastien Deriaz
# License : GPL
"""
Protocol base class. A protocol applies format of outgoing data and removes format
of incoming data

Asumption : A single adapter frame will always be converted to a single protocol frame.
This could change later
"""

import asyncio
import threading
import time
from abc import abstractmethod
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from syndesi.adapters.adapterworker import (
    AdapterClosedEvent,
    AdapterEvent,
    AdapterOpenedEvent,
)
from syndesi.adapters.utils import TimeoutParameterType
from syndesi.component import Component, ReadFrame, ReadScope, SyndesiEvent
from syndesi.tools.errors import (
    AdapterDisconnected,
    AdapterReadError,
    AdapterTimeoutError,
    WorkerThreadError,
)

from ..adapters.adapter import Adapter
from ..adapters.bytesadapter import BytesAdapter
from ..tools.log_settings import LoggerAlias

ProtocolFrameT = TypeVar("ProtocolFrameT")

AdapterT = TypeVar("AdapterT", bound=Adapter[Any])

@dataclass
class ProtocolReadFrame(Generic[ProtocolFrameT], ReadFrame[ProtocolFrameT]):
    """Protocol read frame"""

    # payload: ProtocolFrameT

    # @abstractmethod
    def __str__(self) -> str:
        return f"ProtocolReadFrame({self.data!r})"

@dataclass
class ProtocolWriteFrame(Generic[ProtocolFrameT], ReadFrame[ProtocolFrameT]):
    """Protocol write frame"""
    def __str__(self) -> str:
        return f"ProtocolWriteFrame({self.data!r})"

class ProtocolEvent(SyndesiEvent):
    """Protocol event"""

class ProtocolDisconnectedEvent(ProtocolEvent):
    """Protocol disconnected event"""

@dataclass
class ProtocolFrameEvent(ProtocolEvent, Generic[ProtocolFrameT]):
    """Protocol frame event"""
    frame: ProtocolReadFrame[ProtocolFrameT]

@dataclass
class ProtocolBufferEvent(ProtocolEvent):
    """Event in the protocol frame buffer (frames added or removed)"""
    added_frame_ids : list[int]
    removed_frame_ids : list[int]

# @dataclass
# class ProtocolReadEvent(Generic[ProtocolFrameT], ProtocolEvent):
#     """Protocol read event"""
#     from_buffer : bool
#     frame: ProtocolReadFrame[ProtocolFrameT]

# @dataclass
# class ProtocolWriteEvent(Generic[ProtocolFrameT], ProtocolEvent):
#     """Protocol write event"""
#     frame: ProtocolWriteFrame[ProtocolFrameT]


@dataclass
class _PendingProtocolRead(Generic[ProtocolFrameT]):
    """A single outstanding protocol.read_detailed() call waiting for a frame."""

    future: "Future[ProtocolReadFrame[ProtocolFrameT]]"
    scope: ReadScope
    start_time: float


class Protocol(Generic[AdapterT, ProtocolFrameT], Component[ProtocolFrameT]):
    """
    Base class for protocol layers.

    The first generic parameter describes the adapter type expected by the
    protocol (for example ``BytesAdapter`` or a more specific adapter class).
    The second parameter describes the protocol payload type.

    A Protocol continuously drains its Adapter in the background (one
    permanently re-armed scope=BUFFERED read) so that every incoming frame is
    decoded exactly once, the moment it arrives - whether or not anyone is
    currently waiting on read_detailed(). This runs on the Adapter's existing
    worker thread (via Future.add_done_callback), no extra thread is created.
    Because of this, the Adapter's own pending-read slot is permanently taken:
    once wrapped in a Protocol, reading the Adapter directly is not supported.
    """
    _FRAME_BUFFER_MAX = 256

    def __init__(
        self,
        adapter: AdapterT,
        timeout: TimeoutParameterType = ...,
    ) -> None:
        super().__init__(LoggerAlias.PROTOCOL)
        self.adapter = adapter # adapter is public as it is used in ui
        self._event_callbacks : list[Callable[[ProtocolEvent], None]] = []

        self._frame_id = 0
        self._last_write_timestamp: float | None = None

        self._lock = threading.Lock()
        self._frame_buffer: deque[ProtocolReadFrame[ProtocolFrameT]] = deque(
            maxlen=self._FRAME_BUFFER_MAX
        )
        self._pending: _PendingProtocolRead[ProtocolFrameT] | None = None

        self.adapter.register_event_callback(self._on_lifecycle_event)

        if timeout is not ...:
            self.adapter.set_default_timeout(timeout)

        if timeout is ...:
            self.adapter.set_timeout(self.default_timeout())
        else:
            self.adapter.set_timeout(timeout)

        if self.adapter.is_open():
            self._arm_drain()

    def _next_frame_id(self) -> int:
        output = self._frame_id
        self._frame_id += 1
        return output

    @staticmethod
    @abstractmethod
    def default_timeout() -> float | None:
        """Default timeout"""

    # ┌──────────────────────────────────────┐
    # │ Background drain (decode-once, no    │
    # │ extra thread - see class docstring)  │
    # └──────────────────────────────────────┘

    def _arm_drain(self) -> None:
        # Bypasses Adapter's public locked API on purpose: this is a background,
        # non-blocking re-arm (add_done_callback never waits), not a user operation.
        future = self.adapter._read_detailed_future(  # pylint: disable=protected-access
            timeout=None, scope=ReadScope.BUFFERED, stop_conditions=...
        )
        future.add_done_callback(self._on_adapter_frame)

    def _on_adapter_frame(self, future: "Future[ReadFrame[Any]]") -> None:
        try:
            adapter_frame = future.result()
        except (AdapterDisconnected, AdapterReadError):
            # Adapter closed itself; _on_lifecycle_event handles cleanup and
            # AdapterOpenedEvent (on reconnect) re-arms the drain.
            return

        try:
            protocol_frame = self._adapter_to_protocol(adapter_frame)
        except Exception:  # pylint: disable=broad-exception-caught
            self._logger.exception("Failed to decode frame, dropping it")
            self._arm_drain()
            return

        resolved: Future[ProtocolReadFrame[ProtocolFrameT]] | None = None
        buffered = False
        with self._lock:
            pending = self._pending
            if pending is not None and self._frame_matches_scope(
                protocol_frame, pending.scope, pending.start_time
            ):
                self._pending = None
                resolved = pending.future
            else:
                self._frame_buffer.append(protocol_frame)
                buffered = True

        if resolved is not None:
            resolved.set_result(protocol_frame)
        self._emit_event(ProtocolFrameEvent(frame=protocol_frame))
        if buffered:
            self._emit_event(
                ProtocolBufferEvent(added_frame_ids=[protocol_frame.id], removed_frame_ids=[])
            )
        self._arm_drain()

    def _on_lifecycle_event(self, event: AdapterEvent) -> None:
        if isinstance(event, AdapterClosedEvent):
            with self._lock:
                cleared_ids = [frame.id for frame in self._frame_buffer]
                self._frame_buffer.clear()
                pending = self._pending
                self._pending = None
            if pending is not None:
                pending.future.set_exception(AdapterDisconnected())
            if cleared_ids:
                self._emit_event(
                    ProtocolBufferEvent(added_frame_ids=[], removed_frame_ids=cleared_ids)
                )
            self._emit_event(ProtocolDisconnectedEvent())
        elif isinstance(event, AdapterOpenedEvent):
            self._arm_drain()

    # ┌──────────────────────────────────┐
    # │ Local buffer / pending-read glue │
    # └──────────────────────────────────┘

    def _frame_matches_scope(
        self, frame: ProtocolReadFrame[ProtocolFrameT], scope: ReadScope, call_start: float
    ) -> bool:
        if scope == ReadScope.BUFFERED:
            return True
        if scope == ReadScope.NEXT:
            return frame.stop_timestamp > call_start
        if scope == ReadScope.LAST_WRITE:
            return (
                self._last_write_timestamp is not None
                and frame.first_fragment_timestamp >= self._last_write_timestamp
            )
        return False

    def _pop_matching_locked(
        self, scope: ReadScope, call_start: float
    ) -> ProtocolReadFrame[ProtocolFrameT] | None:
        for index, frame in enumerate(self._frame_buffer):
            if self._frame_matches_scope(frame, scope, call_start):
                del self._frame_buffer[index]
                return frame
        return None

    def _begin_read(
        self, scope: ReadScope, call_start: float
    ) -> tuple[
        ProtocolReadFrame[ProtocolFrameT] | None,
        "Future[ProtocolReadFrame[ProtocolFrameT]] | None",
    ]:
        with self._lock:
            frame = self._pop_matching_locked(scope, call_start)
            if frame is None:
                if self._pending is not None:
                    raise WorkerThreadError("Concurrent read is not supported")
                future: Future[ProtocolReadFrame[ProtocolFrameT]] = Future()
                self._pending = _PendingProtocolRead(
                    future=future, scope=scope, start_time=call_start
                )

        if frame is not None:
            self._emit_event(
                ProtocolBufferEvent(added_frame_ids=[], removed_frame_ids=[frame.id])
            )
            return frame, None
        return None, future

    def _cancel_pending_if_timed_out(self, future: "Future[ProtocolReadFrame[ProtocolFrameT]]") -> None:
        with self._lock:
            if self._pending is not None and self._pending.future is future:
                self._pending = None

    @abstractmethod
    def _adapter_to_protocol(
        self, adapter_frame: ReadFrame[Any]
    ) -> ProtocolReadFrame[ProtocolFrameT]: ...

    @abstractmethod
    def _protocol_to_adapter(
        self, protocol_payload: ProtocolFrameT
    ) -> Any: ...

    def _emit_event(self, event : ProtocolEvent):
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Never let user callback break worker
                self._logger.exception(
                    "Protocol event callback failed with error : %s", str(e)
                )

    def register_event_callback(self, event_callback: Callable[[ProtocolEvent], None]) -> None:
        self._event_callbacks.append(event_callback)

    def clear_event_callbacks(self) -> None:
        self._event_callbacks.clear()

    # ┌────────────┐
    # │ Public API │
    # └────────────┘

    @property
    def frame_buffer(self) -> list[ProtocolReadFrame[ProtocolFrameT]]:
        with self._lock:
            return list(self._frame_buffer)

    # ==== open ====

    def open(self) -> None:
        """
        Open protocol communication with the target (blocking)
        """
        self.adapter.open()

    async def aopen(self) -> None:
        """
        Open protocol communication with the target (async)
        """
        await self.adapter.aopen()

    # ==== close ====

    def close(self) -> None:
        """
        Close protocol communication with the target (blocking)
        """
        self.adapter.close()

    async def aclose(self) -> None:
        """
        Close protocol communication with the target (async)
        """
        await self.adapter.aclose()

    # ==== read_detailed ====

    def read_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED,
    ) -> ProtocolReadFrame[ProtocolFrameT]:
        frame, future = self._begin_read(ReadScope(scope), time.time())
        if frame is not None:
            return frame
        assert future is not None
        resolved_timeout = self.adapter.timeout if timeout is ... else timeout
        try:
            return future.result(resolved_timeout)
        except TimeoutError as e:
            self._cancel_pending_if_timed_out(future)
            raise AdapterTimeoutError(
                float("nan") if resolved_timeout is None else resolved_timeout
            ) from e

    async def aread_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED,
    ) -> ProtocolReadFrame[ProtocolFrameT]:
        frame, future = self._begin_read(ReadScope(scope), time.time())
        if frame is not None:
            return frame
        assert future is not None
        resolved_timeout = self.adapter.timeout if timeout is ... else timeout
        try:
            return await asyncio.wait_for(asyncio.wrap_future(future), resolved_timeout)
        except (TimeoutError, asyncio.TimeoutError) as e:
            self._cancel_pending_if_timed_out(future)
            raise AdapterTimeoutError(
                float("nan") if resolved_timeout is None else resolved_timeout
            ) from e

    # ==== read ====

    async def aread(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> ProtocolFrameT:
        frame = await self.aread_detailed(timeout=timeout, scope=scope)
        return frame.data

    def read(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> ProtocolFrameT:
        frame = self.read_detailed(timeout=timeout, scope=scope)
        return frame.data

    # ==== flush_read ====

    def flush_read(self) -> None:
        """
        Clear read buffer (blocking)
        """
        self.adapter.flush_read()
        with self._lock:
            cleared_ids = [frame.id for frame in self._frame_buffer]
            self._frame_buffer.clear()
        if cleared_ids:
            self._emit_event(
                ProtocolBufferEvent(added_frame_ids=[], removed_frame_ids=cleared_ids)
            )

    async def aflush_read(self) -> None:
        """
        Clear read buffer (async)
        """
        await self.adapter.aflush_read()
        with self._lock:
            cleared_ids = [frame.id for frame in self._frame_buffer]
            self._frame_buffer.clear()
        if cleared_ids:
            self._emit_event(
                ProtocolBufferEvent(added_frame_ids=[], removed_frame_ids=cleared_ids)
            )

    # ==== write ====

    async def awrite(self, data: ProtocolFrameT) -> None:
        await self.adapter.awrite(self._protocol_to_adapter(data))
        self._last_write_timestamp = time.time()

    def write(self, data: ProtocolFrameT) -> None:
        self.adapter.write(self._protocol_to_adapter(data))
        self._last_write_timestamp = time.time()


class BytesProtocol(Protocol[BytesAdapter, ProtocolFrameT], Generic[ProtocolFrameT]):
    """Convenience base class for protocols that operate on byte-oriented adapters."""

    # ==== query_detailed ====

    async def aquery_detailed(
        self,
        payload: ProtocolFrameT,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.LAST_WRITE.value,
    ) -> ProtocolReadFrame[ProtocolFrameT]:
        await self.aflush_read()
        await self.awrite(payload)
        return await self.aread_detailed(timeout=timeout, scope=scope)

    def query_detailed(
        self,
        payload: ProtocolFrameT,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.LAST_WRITE.value,
    ) -> ProtocolReadFrame[ProtocolFrameT]:
        self.flush_read()
        self.write(payload)
        return self.read_detailed(timeout=timeout, scope=scope)

    # ==== Other ====

    def is_open(self) -> bool:
        """
        Return True if the protocol is opened
        """
        return self.adapter.is_open()
