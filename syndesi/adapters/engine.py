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
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass
from enum import StrEnum
from types import EllipsisType
from typing import Any, Generic, TypeVar

from ..tools.errors import (
    AdapterDisconnectedError,
    AdapterError,
    AdapterOpenError,
    AdapterReadError,
    AdapterTimeoutError,
    AdapterWriteError,
    WorkerThreadError,
)
from ..tools.log_settings import LoggerAlias
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
from .framer import (
    AdapterReadFrame,
    AssembledFrame,
    Framer,
    SupportsStopConditions,
    WriteFrame,
)
from .reactor import default_reactor
from .stop_conditions import StopCondition
from .tracehub import tracehub
from .utils import Fragment, HasFileno, TimeoutParameterType, TimeoutType, nmin


class Descriptor(ABC):
    """
    Descriptor base class. A descriptor is a string to define the main parameters
    of an adapter (ip address, port, baudrate, etc...)
    """

    DETECTION_PATTERN = ""

    def __init__(self) -> None:
        return None

    @staticmethod
    @abstractmethod
    def from_string(string: str) -> Descriptor:
        """
        Create a Descriptor class from a string
        """

    @abstractmethod
    def is_initialized(self) -> bool:
        """Return True if the descriptor is initialized"""


DataT = TypeVar("DataT")
ResultT = TypeVar("ResultT")
CommandT = TypeVar("CommandT", bound="Command[Any]")
DescriptorT = TypeVar("DescriptorT", bound=Descriptor)


class ReadScope(StrEnum):
    """
    Read scope

    NEXT : Only read data after the start of the read() call
    BUFFERED : Return any data that was present before the read() call
    LAST_WRITE : Return data received after the last write() call
    """

    NEXT = "next"
    BUFFERED = "buffered"
    LAST_WRITE = "last_write"


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


class ReadCommand(Generic[DataT], Command[AdapterReadFrame[DataT]]):
    """
    Read one frame

    timeout
        ``...`` engine timeout, ``None`` no response timeout, otherwise seconds
    scope
        ``NEXT`` only data arriving after the call, ``BUFFERED`` accept a stored
        frame, ``LAST_WRITE`` only data arriving after the last write
    stop_conditions
        ``...`` keep the framer conditions, otherwise override them for this read

    It can be cancelled while it waits for a frame, the read slot is then freed and the
    next frame goes to the buffer
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


class AdapterBackend(Generic[DescriptorT, DataT], ABC):
    """
    The hardware dialogue of one transport, and nothing else

    A backend is blocking and bare : it holds no thread, no queue and no state about
    reads in flight. Every method below is called on the reactor thread, and only
    while the engine knows the backend is in the matching state

    Parameters
    ----------
    descriptor : Descriptor
    """

    def __init__(self, descriptor: DescriptorT) -> None:
        super().__init__()
        self.descriptor = descriptor

    @abstractmethod
    def selectable(self) -> HasFileno | None:
        """
        Object the reactor watches for incoming data, None while there is nothing
        to watch. A transport without a usable fileno (Visa, serial on Windows) runs
        its own reader thread and returns one end of a socketpair here
        """

    @abstractmethod
    def write(self, data: DataT) -> None:
        """Write data to the target, entirely. Raises an AdapterError on failure"""

    @abstractmethod
    def read(self, fragment_timestamp: float) -> Fragment[DataT]:
        """
        Read one fragment, called only when selectable() reported data available

        fragment_timestamp is the time the reactor saw the data, it is what the
        stop-conditions work with, so it is taken once and passed down rather than
        read again here
        """

    @abstractmethod
    def open(self, timeout: float | None) -> None:
        """Open the communication, raising AdapterOpenError if it cannot"""

    @abstractmethod
    def close(self) -> None:
        """Close the communication. Called even when it is already closed"""

    @property
    @abstractmethod
    def default_timeout(self) -> TimeoutType:
        """Timeout of an adapter built on this backend without an explicit one"""

    # @property
    # @abstractmethod
    # def default_stop_conditions(self) -> list[StopCondition]: ...


# pylint: disable=too-many-instance-attributes
class AdapterEngine(Generic[DescriptorT, DataT]):
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
        timeout: TimeoutParameterType,
        alias: str,
        auto_open: bool,
        # reactor: Reactor | None = None,
    ) -> None:
        self._backend = backend
        self._framer = framer

        if timeout is ...:
            self._timeout = backend.default_timeout
        else:
            self._timeout = timeout

        self.alias = alias

        # self._descriptor = backend.
        self._logger = logging.getLogger(LoggerAlias.ENGINE.value)

        # SimpleQueue because its put() is reentrant : stop() is called by the finalizer
        # of an endpoint, which the garbage collector can run on the reactor thread while
        # it is inside get(). A Queue would deadlock the reactor on its own lock there
        self._commands: queue.SimpleQueue[Command[Any]] = queue.SimpleQueue()
        self._callbacks: list[Callable[[AdapterEvent], None]] = []

        self.frame_buffer: deque[AdapterReadFrame[DataT]] = deque(
            maxlen=self._FRAME_BUFFER_MAX
        )
        self._frame_id = 0
        self._pending_read: PendingRead[DataT] | None = None
        self._last_write_timestamp: float | None = None
        self._is_open = False
        # Why the last open failed, raised by the operations that need the target open
        self._open_error: str | None = None

        self._reactor = default_reactor()  # if reactor is None else reactor
        self._reactor.attach(self)

        # Submitted, not waited for : the sync facade waits on it in its __init__, the
        # async one lets it run behind the first operation. Skipped while the descriptor
        # is incomplete, a protocol may still have to set a default (port, baudrate, ...)
        # self._auto_open: OpenCommand | None = None
        if auto_open and backend.descriptor.is_initialized():
            self.open().result()
        # if auto_open and backend.descriptor.is_initialized():
        #     self._auto_open = self.open()

    # def __str__(self) -> str:
    #     return f"Engine({self._backend.descriptor})"

    # ┌────────────────────────────────┐
    # │ User interface, returns futures │
    # └────────────────────────────────┘

    @property
    def descriptor(self) -> DescriptorT:
        """Backend descriptor"""
        return self._backend.descriptor

    # @property
    # def auto_open_command(self) -> OpenCommand | None:
    #     """The open submitted at construction, None if there was none to submit"""
    #     return self._auto_open

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
        output = self._submit(WriteCommand(WriteFrame(data=data)))
        return output

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

    def set_stop_conditions(
        self, stop_conditions: list[StopCondition]
    ) -> SetStopConditionsCommand:
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

    def selectable(self) -> HasFileno | None:
        """Object the reactor watches for this engine, see AdapterBackend"""
        return self._backend.selectable()

    # ┌───────────────────┐
    # │ Reactor interface │
    # └───────────────────┘

    def next_deadline(self) -> float | None:
        """Earliest timestamp at which on_deadline must be called"""
        deadline = self._framer.next_deadline()
        pending = self._pending_read
        if pending is not None and self._response_deadline_applies(deadline):
            deadline = nmin(deadline, pending.response_deadline)
        return deadline

    def _response_deadline_applies(self, framer_deadline: float | None) -> bool:
        """
        True if the response timeout of the pending read still counts

        It stops counting once data starts arriving : the stop-conditions take over and
        decide when the frame ends. But if none of them is time based (Termination,
        Length) there would be no deadline left at all, and the read would hang forever
        """
        return not self._framer.in_progress or framer_deadline is None

    def drain_commands(self) -> None:
        """Run every queued command"""
        self._drop_cancelled_read()
        while True:
            try:
                command = self._commands.get(block=False)
            except queue.Empty:
                return
            # A read stays cancellable while it waits for a frame. Any other command
            # completes right here, so it is claimed first : cancelled before this point
            # it is skipped, after it the cancel comes too late
            if not isinstance(command, ReadCommand) and not self._claim(command):
                continue
            try:
                self._execute(command)
            except Exception as e:  # pylint: disable=broad-exception-caught
                self._fail(command, e)

    def on_readable(self, now: float) -> None:
        """The backend has data available"""
        try:
            fragment = self._backend.read(now)
        except AdapterError as e:
            self._fail_and_close(e)
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
            and self._response_deadline_applies(self._framer.next_deadline())
            and pending.response_deadline is not None
            and now >= pending.response_deadline
        ):
            self._fail_read_timeout(pending)

        for frame in self._framer.on_deadline(now):
            self._deliver(frame)

    # ┌──────────┐
    # │ Commands │
    # └──────────┘

    @staticmethod
    def _claim(command: Command[Any]) -> bool:
        """
        Take a command for completion, False if its caller cancelled it

        A claimed command can't be cancelled anymore, so its result can't race with the
        caller giving up on it
        """
        if command.running():
            return True
        if command.done():
            return False
        return command.set_running_or_notify_cancel()

    @classmethod
    def _fail(cls, command: Command[Any], error: BaseException) -> None:
        """Fail a command, unless its caller cancelled it"""
        if cls._claim(command):
            command.set_exception(error)

    # pylint: disable=too-many-branches
    def _execute(self, command: Command[Any]) -> None:
        match command:
            case OpenCommand():
                self._open_command(command)
            case CloseCommand():
                self._close_command(clear_buffer=True)
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
                    self._framer.set_stop_conditions(command.stop_conditions)
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
                self._close_command(clear_buffer=True)
                self._reactor.detach(self)
                command.set_result(None)
            case _:
                command.set_exception(WorkerThreadError(f"Unknown command {command!r}"))

    def _open_command(self, command: OpenCommand) -> None:
        if self._is_open:
            command.set_result(None)
            return
        if not self._backend.descriptor.is_initialized():
            command.set_exception(AdapterOpenError("Descriptor is not initialized"))
            return
        try:
            self._backend.open(self._timeout)
        except AdapterError as e:
            self._logger.error(str(e))
            self._open_error = str(e)
            command.set_exception(e)
            return
        self._is_open = True
        self._open_error = None
        tracehub.emit_open(str(self._backend.descriptor))
        self._logger.info(f"{self._backend.descriptor} opened")
        command.set_result(None)
        self._emit(AdapterOpenedEvent())

    def _close_command(self, clear_buffer: bool) -> None:
        self._open_error = None
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
            self._fail(pending.command, AdapterDisconnectedError())

        self._emit(AdapterClosedEvent())

    def _write(self, command: WriteCommand[DataT]) -> None:
        if not self._is_open:
            command.set_exception(
                self._not_open_error(AdapterWriteError("Adapter is not opened"))
            )
            return
        self._last_write_timestamp = time.time()
        try:
            self._backend.write(command.frame.data)
        except AdapterError as e:
            command.set_exception(e)
            return
        tracehub.emit_write_frame(str(self._backend.descriptor), command.frame)
        command.set_result(None)
        self._emit(AdapterWriteEvent(command.frame))

    # ┌───────┐
    # │ Reads │
    # └───────┘

    def _begin_read(self, command: ReadCommand[DataT]) -> None:
        now = time.time()

        if command.cancelled():
            return

        if self._pending_read is not None:
            self._fail(command, WorkerThreadError("Concurrent read is not supported"))
            return

        if command.scope == ReadScope.LAST_WRITE and self._last_write_timestamp is None:
            self._fail(
                command,
                AdapterReadError(
                    "Cannot read with scope=LAST_WRITE without a previous write"
                ),
            )
            return

        buffered_index = self._buffered_index(command.scope)
        if buffered_index is not None:
            if self._claim(command):
                frame = self.frame_buffer[buffered_index]
                del self.frame_buffer[buffered_index]
                command.set_result(frame)
                self._emit(
                    AdapterBufferEvent(added_frame_ids=[], removed_frame_ids=[frame.id])
                )
                self._emit(AdapterReadEvent(frame, from_buffer=True))
            return

        # A closed engine receives nothing, fail now instead of at the timeout
        if not self._is_open:
            self._fail(
                command, self._not_open_error(AdapterReadError("Adapter is not opened"))
            )
            return

        timeout = self._resolve_timeout(command.timeout)
        pending = PendingRead(
            command=command,
            start_time=now,
            scope=command.scope,
            response_deadline=None if timeout is None else now + timeout,
            timeout=timeout,
        )

        if command.stop_conditions is not ... and isinstance(
            self._framer, SupportsStopConditions
        ):
            pending.previous_stop_conditions = self._framer.stop_conditions
            self._framer.set_stop_conditions(
                [command.stop_conditions]
                if isinstance(command.stop_conditions, StopCondition)
                else list(command.stop_conditions)
            )

        self._pending_read = pending
        # A cancel() must free the read slot without waiting for a frame or a deadline
        command.add_done_callback(self._wakeup_if_cancelled)

    def _buffered_index(self, scope: ReadScope) -> int | None:
        """
        Index of the first buffered frame this read can take, None if there is none

        The whole buffer is scanned : with LAST_WRITE a frame older than the write can
        sit at the head, and it must not hide the answer that came after it
        """
        if scope == ReadScope.NEXT:
            return None
        for index, frame in enumerate(self.frame_buffer):
            if scope == ReadScope.LAST_WRITE:
                assert self._last_write_timestamp is not None
                if frame.first_fragment_timestamp < self._last_write_timestamp:
                    continue
            return index
        return None

    def _deliver(self, frame: AssembledFrame[DataT]) -> None:
        read_frame = self._build_read_frame(frame)
        tracehub.emit_read_frame(str(self._backend.descriptor), read_frame)

        pending = self._pending_read
        if pending is not None and pending.command.cancelled():
            # A frame boundary, where a cancelled read can give its stop-conditions back
            self._clear_pending_read(pending)
            pending = None

        if (
            pending is not None
            and self._matches(read_frame, pending)
            and self._claim(pending.command)
        ):
            self._emit(AdapterFrameEvent(read_frame, False))
            self._clear_pending_read(pending)
            pending.command.set_result(read_frame)
            self._emit(AdapterReadEvent(read_frame, from_buffer=False))
        else:
            self._emit(AdapterFrameEvent(read_frame, True))
            self.frame_buffer.append(read_frame)
            self._emit(
                AdapterBufferEvent(
                    added_frame_ids=[read_frame.id], removed_frame_ids=[]
                )
            )

    def _drop_cancelled_read(self) -> None:
        """
        Free the read slot if the caller cancelled its read

        The read may have swapped the framer stop-conditions, which can only be put back
        on a frame boundary. While a frame is being assembled, _deliver frees the slot
        once it completes
        """
        pending = self._pending_read
        if pending is None or not pending.command.cancelled():
            return
        if pending.previous_stop_conditions is not None and self._framer.in_progress:
            return
        self._clear_pending_read(pending)

    def _wakeup_if_cancelled(self, command: Future[Any]) -> None:
        """Done callback of a pending read, runs on the thread that completed it"""
        if command.cancelled():
            self._reactor.wakeup()

    def _matches(
        self, frame: AdapterReadFrame[DataT], pending: PendingRead[DataT]
    ) -> bool:
        if pending.scope == ReadScope.BUFFERED:
            return True
        # first_fragment_timestamp, not stop_timestamp : a frame that started before
        # the read (or before the write) doesn't become recent by ending after it
        if pending.scope == ReadScope.NEXT:
            return frame.first_fragment_timestamp > pending.start_time
        if pending.scope == ReadScope.LAST_WRITE:
            return (
                self._last_write_timestamp is not None
                and frame.first_fragment_timestamp > self._last_write_timestamp
            )
        return False

    def _build_read_frame(
        self, frame: AssembledFrame[DataT]
    ) -> AdapterReadFrame[DataT]:
        """
        Add what the framer cannot know : the frame id and the response delay

        The id counts everything this engine delivered, so it stays unique across
        framer resets and stop-condition overrides. The response delay needs the
        write timestamp, which never reaches the framer
        """
        if self._last_write_timestamp is None:
            response_delay = float("nan")
        else:
            response_delay = frame.first_fragment_timestamp - self._last_write_timestamp

        return AdapterReadFrame(
            data=frame.data,
            id=self._next_frame_id(),
            stop_timestamp=frame.stop_timestamp,
            stop_condition=frame.stop_condition,
            first_fragment_timestamp=frame.first_fragment_timestamp,
            response_delay=response_delay,
        )

    def _fail_read_timeout(self, pending: PendingRead[DataT]) -> None:
        self._clear_pending_read(pending)
        self._fail(
            pending.command,
            AdapterTimeoutError(
                float("nan") if pending.timeout is None else pending.timeout
            ),
        )

    def _fail_and_close(self, error: AdapterError) -> None:
        pending = self._pending_read
        if pending is not None:
            self._clear_pending_read(pending)
            self._fail(pending.command, error)
        # Through the close path, so that is_open, the framer and the events stay
        # consistent. The buffer is kept : frames received before the target went away
        # are still valid. The pending read is already cleared, _close_command won't
        # fail it a second time
        self._close_command(clear_buffer=False)

    def _clear_pending_read(self, pending: PendingRead[DataT]) -> None:
        self._pending_read = None
        if pending.previous_stop_conditions is not None and isinstance(
            self._framer, SupportsStopConditions
        ):
            self._framer.set_stop_conditions(pending.previous_stop_conditions)
            pending.previous_stop_conditions = None

    # ┌────────┐
    # │ Common │
    # └────────┘

    def _not_open_error(self, error: AdapterError) -> AdapterError:
        """
        Error of an operation that needs the target open

        If the last open failed its reason is raised instead, that's how an open
        submitted without waiting (AsyncEndpoint auto_open) reports its failure
        """
        if self._open_error is not None:
            return AdapterOpenError(self._open_error)
        return error

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
