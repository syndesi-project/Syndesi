# File : engine.py
# Author : Sébastien Deriaz
# License : GPL
"""
Engine, the neutral layer between a backend and the user facades

The engine knows neither sync nor async. Every operation is submitted as a command
and returns a Future, which the sync facade resolves with result() and the async one
with asyncio.wrap_future()

All the methods in the "Reactor interface" section run on the reactor thread and
must not be called by the user. Everything else is thread safe
"""

from __future__ import annotations

import logging
import queue
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from types import EllipsisType
from typing import Any, Generic, TypeVar

from ..component import Descriptor, ReadFrame, ReadScope, WriteFrame
from ..tools.errors import (
    AdapterDisconnected,
    AdapterError,
    AdapterOpenError,
    AdapterReadError,
    AdapterTimeoutError,
    AdapterWriteError,
    WorkerThreadError,
)
from ..tools.log_settings import LoggerAlias
from .backend import (
    AdapterBackend,
    BackendDisconnectedError,
    BackendError,
    BackendOpenError,
    BackendReadError,
    BackendWriteError,
)
from .events import (
    AdapterBufferEvent,
    AdapterClosedEvent,
    AdapterEvent,
    AdapterFragmentEvent,
    AdapterFrameEvent,
    AdapterOpenedEvent,
    AdapterReadEvent,
    AdapterStopConditionsUpdatedEvent,
    AdapterTimeoutUpdatedEvent,
    AdapterWriteEvent,
)
from .framer import Frame, Framer, SupportsStopConditions
from .reactor import Reactor, default_reactor
from .stop_conditions import StopCondition
from .tracehub import tracehub
from .utils import Fragment, HasFileno, TimeoutParameterType, TimeoutType, nmin

DataT = TypeVar("DataT")
ResultT = TypeVar("ResultT")
CommandT = TypeVar("CommandT", bound="Command[Any]")
DescriptorT = TypeVar("DescriptorT", bound=Descriptor)

_BACKEND_ERRORS: dict[type[BackendError], type[AdapterError]] = {
    BackendOpenError: AdapterOpenError,
    BackendDisconnectedError: AdapterDisconnected,
    BackendReadError: AdapterReadError,
    BackendWriteError: AdapterWriteError,
}


def adapter_error(error: BackendError) -> AdapterError:
    """
    Translate a backend error into the adapter error the user sees
    """
    return _BACKEND_ERRORS.get(type(error), AdapterError)(str(error))


# ┌──────────┐
# │ Commands │
# └──────────┘


class Command(Future[ResultT]):
    """
    Command submitted to the engine and completed on the reactor thread

    A timeout on result() means the reactor didn't answer, not that the target
    didn't. Target timeouts are raised as AdapterTimeoutError by the engine itself
    """

    def result(self, timeout: float | None = None) -> ResultT:
        """
        Wait for the reactor to complete the command and return its result
        """
        try:
            return super().result(timeout=timeout)
        except TimeoutError:
            raise WorkerThreadError(
                f"No response from the reactor to {type(self).__name__} within {timeout}s"
            ) from None


class OpenCommand(Command[None]):
    """Open the backend"""


class CloseCommand(Command[None]):
    """Close the backend"""


class ClearBufferCommand(Command[None]):
    """Drop the buffered frames and the frame being assembled"""


class StopCommand(Command[None]):
    """Detach the engine from the reactor"""


class ClearEventCallbacksCommand(Command[None]):
    """Remove every event callback"""


class GetStopConditionsCommand(Command["list[StopCondition]"]):
    """Return the stop-conditions currently used by the framer"""


class WriteCommand(Generic[DataT], Command[None]):
    """Write data to the target"""

    def __init__(self, frame: WriteFrame[DataT]) -> None:
        super().__init__()
        self.frame = frame


class SetTimeoutCommand(Command[None]):
    """Set the engine timeout"""

    def __init__(self, timeout: TimeoutType) -> None:
        super().__init__()
        self.timeout = timeout


class SetStopConditionsCommand(Command[None]):
    """Set the framer stop-conditions"""

    def __init__(self, stop_conditions: list[StopCondition]) -> None:
        super().__init__()
        self.stop_conditions = stop_conditions


class AddEventCallbackCommand(Command[None]):
    """Register an event callback"""

    def __init__(self, callback: Callable[[AdapterEvent], None]) -> None:
        super().__init__()
        self.callback = callback


class ReadCommand(Generic[DataT], Command["ReadFrame[DataT]"]):
    """
    Read one frame

    timeout
        ``...`` engine timeout, ``None`` no response timeout, otherwise seconds
    scope
        ``NEXT`` only data arriving after the call, ``BUFFERED`` accept a stored
        frame, ``LAST_WRITE`` only data arriving after the last write
    stop_conditions
        ``...`` keep the framer conditions, otherwise override them for this read
    """

    def __init__(
        self,
        timeout: TimeoutParameterType,
        scope: ReadScope,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType,
    ) -> None:
        super().__init__()
        self.timeout = timeout
        self.scope = scope
        self.stop_conditions = stop_conditions


@dataclass
class PendingRead(Generic[DataT]):
    """
    The single outstanding read, held by the engine until a frame matches it
    """

    command: ReadCommand[DataT]
    start_time: float
    scope: ReadScope
    response_deadline: float | None
    timeout: TimeoutType
    previous_stop_conditions: list[StopCondition] | None = None


# ┌────────┐
# │ Engine │
# └────────┘


# pylint: disable=too-many-instance-attributes
class Engine(Generic[DescriptorT, DataT]):
    """
    Drives one backend on the reactor thread and exposes it as futures

    Parameters
    ----------
    backend : AdapterBackend
    framer : Framer
    timeout : float | int | None
    alias : str
    reactor : Reactor or None
        Default shared reactor if None
    """

    _FRAME_BUFFER_MAX = 256

    def __init__(
        self,
        backend: AdapterBackend[DescriptorT, DataT],
        framer: Framer[DataT],
        *,
        timeout: TimeoutType,
        alias: str = "",
        reactor: Reactor | None = None,
    ) -> None:
        self._backend = backend
        self._framer = framer
        self._timeout = timeout
        self.alias = alias

        self._logger = logging.getLogger(LoggerAlias.ENGINE.value)

        self._commands: queue.Queue[Command[Any]] = queue.Queue()
        self._callbacks: list[Callable[[AdapterEvent], None]] = []

        self.frame_buffer: deque[ReadFrame[DataT]] = deque(maxlen=self._FRAME_BUFFER_MAX)
        self._frame_id = 0
        self._pending_read: PendingRead[DataT] | None = None
        self._last_write_timestamp: float | None = None
        self._is_open = False

        self._reactor = default_reactor() if reactor is None else reactor
        self._reactor.attach(self)

    def __str__(self) -> str:
        return f"Engine({self._backend.descriptor})"

    # ┌────────────────────────────────┐
    # │ User interface, returns futures │
    # └────────────────────────────────┘

    @property
    def descriptor(self) -> DescriptorT:
        """Backend descriptor"""
        return self._backend.descriptor

    @property
    def is_open(self) -> bool:
        """True if the backend is open"""
        return self._is_open

    @property
    def timeout(self) -> TimeoutType:
        """Engine timeout, used when a read doesn't specify one"""
        return self._timeout

    @property
    def stop_conditions(self) -> list[StopCondition]:
        """Framer stop-conditions, empty if the framer doesn't use any"""
        if isinstance(self._framer, SupportsStopConditions):
            return list(self._framer.stop_conditions)
        return []

    def open(self) -> OpenCommand:
        """Open the backend"""
        return self._submit(OpenCommand())

    def close(self) -> CloseCommand:
        """Close the backend"""
        return self._submit(CloseCommand())

    def write(self, data: DataT) -> WriteCommand[DataT]:
        """Write data to the target"""
        return self._submit(WriteCommand(WriteFrame(data)))

    def read(
        self,
        timeout: TimeoutParameterType = ...,
        scope: ReadScope = ReadScope.BUFFERED,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
    ) -> ReadCommand[DataT]:
        """Read one frame"""
        return self._submit(ReadCommand(timeout, scope, stop_conditions))

    def clear_buffer(self) -> ClearBufferCommand:
        """Drop every buffered frame"""
        return self._submit(ClearBufferCommand())

    def set_timeout(self, timeout: TimeoutType) -> SetTimeoutCommand:
        """Set the engine timeout"""
        return self._submit(SetTimeoutCommand(timeout))

    def set_stop_conditions(self, stop_conditions: list[StopCondition]) -> SetStopConditionsCommand:
        """Set the framer stop-conditions"""
        return self._submit(SetStopConditionsCommand(stop_conditions))

    def get_stop_conditions(self) -> GetStopConditionsCommand:
        """Return the framer stop-conditions"""
        return self._submit(GetStopConditionsCommand())

    def register_event_callback(
        self, callback: Callable[[AdapterEvent], None]
    ) -> AddEventCallbackCommand:
        """Register an event callback, called on the reactor thread"""
        return self._submit(AddEventCallbackCommand(callback))

    def clear_event_callbacks(self) -> ClearEventCallbacksCommand:
        """Remove every event callback"""
        return self._submit(ClearEventCallbacksCommand())

    def stop(self) -> StopCommand:
        """Close the backend and detach the engine from the reactor"""
        return self._submit(StopCommand())

    def _submit(self, command: CommandT) -> CommandT:
        self._commands.put(command)
        self._reactor.wakeup()
        return command

    # ┌───────────────────┐
    # │ Reactor interface │
    # └───────────────────┘

    def selectable(self) -> HasFileno | None:
        """Object to watch for incoming data, None if there is nothing to watch"""
        return self._backend.selectable()

    def next_deadline(self) -> float | None:
        """Earliest timestamp at which on_deadline must be called"""
        deadline = self._framer.next_deadline()
        pending = self._pending_read
        if pending is not None and not self._framer.in_progress:
            deadline = nmin(deadline, pending.response_deadline)
        return deadline

    def drain_commands(self) -> None:
        """Run every queued command"""
        while True:
            try:
                command = self._commands.get(block=False)
            except queue.Empty:
                return
            try:
                self._execute(command)
            except Exception as e:  # pylint: disable=broad-exception-caught
                if not command.done():
                    command.set_exception(e)

    def on_readable(self, now: float) -> None:
        """The backend has data available"""
        try:
            fragment = self._backend.read(now)
        except BackendError as e:
            self._fail_and_close(adapter_error(e))
            return

        first = not self._framer.in_progress
        frames = self._framer.push(fragment)
        self._emit_fragment(fragment, first)

        for frame in frames:
            self._deliver(frame)

    def on_deadline(self, now: float) -> None:
        """A deadline returned by next_deadline has been reached"""
        pending = self._pending_read
        if (
            pending is not None
            and not self._framer.in_progress
            and pending.response_deadline is not None
            and now >= pending.response_deadline
        ):
            self._fail_read_timeout(pending)

        for frame in self._framer.on_deadline(now):
            self._deliver(frame)

    # ┌──────────┐
    # │ Commands │
    # └──────────┘

    # pylint: disable=too-many-branches
    def _execute(self, command: Command[Any]) -> None:
        match command:
            case OpenCommand():
                self._open_backend(command)
            case CloseCommand():
                self._close_backend(clear_buffer=True)
                command.set_result(None)
            case WriteCommand():
                self._write(command)
            case ReadCommand():
                self._begin_read(command)
            case ClearBufferCommand():
                self._clear_buffer()
                self._framer.reset()
                command.set_result(None)
            case SetTimeoutCommand():
                self._timeout = command.timeout
                command.set_result(None)
                self._emit(AdapterTimeoutUpdatedEvent())
            case SetStopConditionsCommand():
                if isinstance(self._framer, SupportsStopConditions):
                    self._framer.stop_conditions = command.stop_conditions
                command.set_result(None)
                self._emit(AdapterStopConditionsUpdatedEvent())
            case GetStopConditionsCommand():
                command.set_result(self.stop_conditions)
            case AddEventCallbackCommand():
                self._callbacks.append(command.callback)
                command.set_result(None)
            case ClearEventCallbacksCommand():
                self._callbacks.clear()
                command.set_result(None)
            case StopCommand():
                self._close_backend(clear_buffer=True)
                self._reactor.detach(self)
                command.set_result(None)
            case _:
                command.set_exception(WorkerThreadError(f"Unknown command {command!r}"))

    def _open_backend(self, command: OpenCommand) -> None:
        if self._is_open:
            command.set_result(None)
            return
        if not self._backend.descriptor.is_initialized():
            command.set_exception(AdapterOpenError("Descriptor is not initialized"))
            return
        try:
            self._backend.open(self._timeout)
        except BackendError as e:
            self._logger.error(str(e))
            command.set_exception(adapter_error(e))
            return

        self._is_open = True
        tracehub.emit_open(str(self._backend.descriptor))
        self._logger.info(f"{self._backend.descriptor} opened")
        command.set_result(None)
        self._emit(AdapterOpenedEvent())

    def _close_backend(self, clear_buffer: bool) -> None:
        if self._is_open:
            self._backend.close()
            self._is_open = False
            tracehub.emit_close(str(self._backend.descriptor))

        self._framer.reset()
        self._last_write_timestamp = None

        if clear_buffer:
            self._clear_buffer()

        pending = self._pending_read
        if pending is not None:
            self._clear_pending_read(pending)
            pending.command.set_exception(AdapterDisconnected())

        self._emit(AdapterClosedEvent())

    def _write(self, command: WriteCommand[DataT]) -> None:
        if not self._is_open:
            command.set_exception(AdapterWriteError("Adapter is not opened"))
            return
        self._last_write_timestamp = time.time()
        try:
            self._backend.write(command.frame.data)
        except BackendError as e:
            command.set_exception(adapter_error(e))
            return
        tracehub.emit_write_frame(str(self._backend.descriptor), command.frame)
        command.set_result(None)
        self._emit(AdapterWriteEvent(command.frame))

    # ┌───────┐
    # │ Reads │
    # └───────┘

    def _begin_read(self, command: ReadCommand[DataT]) -> None:
        now = time.time()

        if self._pending_read is not None:
            command.set_exception(WorkerThreadError("Concurrent read is not supported"))
            return

        if command.scope == ReadScope.LAST_WRITE and self._last_write_timestamp is None:
            command.set_exception(
                AdapterReadError("Cannot read with scope=LAST_WRITE without a previous write")
            )
            return

        frame = self._pop_buffered(command.scope)
        if frame is not None:
            command.set_result(frame)
            self._emit(AdapterBufferEvent(added_frame_ids=[], removed_frame_ids=[frame.id]))
            self._emit(AdapterReadEvent(frame, from_buffer=True))
            return

        timeout = self._resolve_timeout(command.timeout)
        pending = PendingRead(
            command=command,
            start_time=now,
            scope=command.scope,
            response_deadline=None if timeout is None else now + timeout,
            timeout=timeout,
        )

        if command.stop_conditions is not ... and isinstance(self._framer, SupportsStopConditions):
            pending.previous_stop_conditions = self._framer.stop_conditions
            self._framer.stop_conditions = (
                [command.stop_conditions]
                if isinstance(command.stop_conditions, StopCondition)
                else command.stop_conditions
            )

        self._pending_read = pending

    def _pop_buffered(self, scope: ReadScope) -> ReadFrame[DataT] | None:
        if len(self.frame_buffer) == 0:
            return None
        if scope == ReadScope.NEXT:
            return None
        if scope == ReadScope.LAST_WRITE:
            assert self._last_write_timestamp is not None
            if self.frame_buffer[0].first_fragment_timestamp < self._last_write_timestamp:
                return None
        return self.frame_buffer.popleft()

    def _deliver(self, frame: Frame[DataT]) -> None:
        read_frame = self._build_read_frame(frame)
        tracehub.emit_read_frame(str(self._backend.descriptor), read_frame)

        pending = self._pending_read
        buffered = pending is None or not self._matches(read_frame, pending)

        self._emit(AdapterFrameEvent(read_frame, buffered))

        if buffered:
            self.frame_buffer.append(read_frame)
            self._emit(AdapterBufferEvent(added_frame_ids=[read_frame.id], removed_frame_ids=[]))
        elif pending is not None:
            self._clear_pending_read(pending)
            pending.command.set_result(read_frame)
            self._emit(AdapterReadEvent(read_frame, from_buffer=False))

    def _matches(self, frame: ReadFrame[DataT], pending: PendingRead[DataT]) -> bool:
        if pending.scope == ReadScope.BUFFERED:
            return True
        if pending.scope == ReadScope.NEXT:
            return frame.stop_timestamp > pending.start_time
        if pending.scope == ReadScope.LAST_WRITE:
            return (
                self._last_write_timestamp is not None
                and frame.stop_timestamp > self._last_write_timestamp
            )
        return False

    def _build_read_frame(self, frame: Frame[DataT]) -> ReadFrame[DataT]:
        if self._last_write_timestamp is None:
            response_delay = float("nan")
        else:
            response_delay = frame.first_fragment_timestamp - self._last_write_timestamp

        read_frame: ReadFrame[DataT] = ReadFrame(
            data=frame.data,
            id=self._next_frame_id(),
            stop_timestamp=frame.stop_timestamp,
            previous_read_buffer_used=False,
            response_delay=response_delay,
            stop_condition=frame.stop_condition,
            first_fragment_timestamp=frame.first_fragment_timestamp,
        )
        return read_frame

    def _fail_read_timeout(self, pending: PendingRead[DataT]) -> None:
        self._clear_pending_read(pending)
        pending.command.set_exception(
            AdapterTimeoutError(float("nan") if pending.timeout is None else pending.timeout)
        )

    def _fail_and_close(self, error: AdapterError) -> None:
        pending = self._pending_read
        if pending is not None:
            self._clear_pending_read(pending)
            pending.command.set_exception(error)
        self._close_backend(clear_buffer=False)

    def _clear_pending_read(self, pending: PendingRead[DataT]) -> None:
        self._pending_read = None
        if pending.previous_stop_conditions is not None and isinstance(
            self._framer, SupportsStopConditions
        ):
            self._framer.stop_conditions = pending.previous_stop_conditions
            pending.previous_stop_conditions = None

    # ┌────────┐
    # │ Common │
    # └────────┘

    def _resolve_timeout(self, timeout: TimeoutParameterType) -> TimeoutType:
        if timeout is ...:
            return self._timeout
        if timeout is None:
            return None
        try:
            return float(timeout)
        except (ValueError, TypeError) as e:
            raise AdapterReadError(f"Invalid timeout : {timeout}") from e

    def _next_frame_id(self) -> int:
        output = self._frame_id
        self._frame_id += 1
        return output

    def _clear_buffer(self) -> None:
        if len(self.frame_buffer) == 0:
            return
        removed = [frame.id for frame in self.frame_buffer]
        self.frame_buffer.clear()
        self._emit(AdapterBufferEvent(added_frame_ids=[], removed_frame_ids=removed))

    def _emit_fragment(self, fragment: Fragment[DataT], first: bool) -> None:
        if self._last_write_timestamp is None:
            write_delta = float("nan")
        else:
            write_delta = fragment.timestamp - self._last_write_timestamp
        tracehub.emit_fragment(str(self._backend.descriptor), fragment, write_delta)
        self._emit(AdapterFragmentEvent(fragment, first, self._framer.next_deadline()))

    def _emit(self, event: AdapterEvent) -> None:
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:  # pylint: disable=broad-exception-caught
                self._logger.exception(f"Event callback failed : {e}")
