# File : adapter_worker.py
# Author : Sébastien Deriaz
# License : GPL

"""
Adapter worker mixin and worker command types.
"""

import logging
import queue
import socket
import threading
import time
from abc import abstractmethod
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from select import select
from types import EllipsisType
from typing import Any, Generic, TypeVar

from syndesi.adapters.stop_conditions import StopCondition
from syndesi.tools.log_settings import LoggerAlias

from ..component import Descriptor, Event, Frame, ReadFrame, ReadScope, ThreadCommand, WriteFrame
from ..tools.errors import (
    AdapterDisconnected,
    AdapterOpenError,
    AdapterReadError,
    AdapterTimeoutError,
    AdapterWriteError,
    WorkerThreadError,
)
from .tracehub import tracehub
from .utils import Fragment, HasFileno, TimeoutType, ValidTimeoutType

DataT = TypeVar("DataT")

# ┌────────────────┐
# │ Adapter events │
# └────────────────┘


class AdapterEvent(Event):
    """Adapter event"""

class AdapterClosedEvent(AdapterEvent):
    """Adapter closed event"""

class AdapterOpenedEvent(AdapterEvent):
    """Adapter opened event"""

@dataclass
class AdapterWriteEvent(Generic[DataT], AdapterEvent):
    """Adapter write event, emitted when data has been written"""
    frame: WriteFrame[DataT]

@dataclass
class AdapterReadEvent(Generic[DataT], AdapterEvent):
    """Adapter frame event, emitted when new data is available"""
    frame: ReadFrame[DataT]

@dataclass
class AdapterFragmentEvent(Generic[DataT], AdapterEvent):
    """Adapter fragment event"""
    fragment : Fragment[DataT]
    next_timeout_timestamp: float | None
    first : bool

@dataclass
class AdapterBufferEvent(AdapterEvent):
    added_frame_ids : list[int]
    removed_frame_ids : list[int]

# ┌───────────────────────────────┐
# │ Worker commands (composition) │
# └───────────────────────────────┘

class SetStopConditionsCommand(ThreadCommand[None]):
    """Configure adapter stop conditions"""

    def __init__(self, stop_conditions: list[StopCondition]) -> None:
        super().__init__()
        self.stop_conditions = stop_conditions

class GetStopConditionsCommand(ThreadCommand[list[StopCondition]]):
    """Return the list of stop-conditions"""

class OpenCommand(ThreadCommand[None]):
    """Open the adapter"""


class CloseCommand(ThreadCommand[None]):
    """Close the adapter"""


class StopThreadCommand(ThreadCommand[None]):
    """Stop the worker thread"""


class FlushReadCommand(ThreadCommand[None]):
    """Clear buffered frames and reset worker read state"""


class AddEventCallbackCommand(ThreadCommand[None]):
    """Configure the callback event"""

    def __init__(self, callback: Callable[[AdapterEvent], None]) -> None:
        super().__init__()
        self.event_callback = callback

class ClearEventCallbacksCommand(ThreadCommand[None]):
    """Clear all of the event callbacks"""


class WriteCommand(Generic[DataT], ThreadCommand[None]):
    """Write data to the adapter"""

    def __init__(self, frame: WriteFrame[DataT]) -> None:
        super().__init__()
        self.frame = frame


class SetTimeoutCommand(ThreadCommand[None]):
    """Configure adapter timeout"""

    def __init__(self, timeout: ValidTimeoutType) -> None:
        super().__init__()
        self.timeout = timeout


class IsOpenCommand(ThreadCommand[bool]):
    """Return True if the adapter is opened"""


class ReadCommand(Generic[DataT], ThreadCommand[ReadFrame[DataT]]):
    """
    Read a frame (detailed) from the adapter.

    timeout:
        - ... => use adapter default timeout
        - None => wait indefinitely for first fragment (response timeout disabled)
        - float | int => as provided

    scope:
        - ``ReadScope.NEXT`` => Only read data after the read command
        - ``ReadScope.BUFFERED`` => Accept data that was already in the buffer
        - ``ReadScope.LAST_WRITE`` => Accept data after the last write command
    """

    def __init__(
        self,
        timeout: TimeoutType,
        scope: ReadScope,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> None:
        super().__init__()
        self.timeout = timeout
        self.scope = scope
        self.stop_conditions = stop_conditions


# pylint: disable=too-many-instance-attributes
@dataclass
class PendingRead(Generic[DataT]):
    """
    Worker-thread state for one outstanding read.
    """

    cmd: ReadCommand[DataT]
    start_time: float
    scope: ReadScope
    response_deadline: float | None
    # Stop-condition only
    stop_override: list[StopCondition] | None = None
    first_fragment_seen: bool = False
    stop_override_applied: bool = False
    prev_stop_conditions: list[StopCondition] | None = None


class AdapterWorkerInterface(Generic[DataT]):
    """Adapter base class for worker interface.
    The worker will call these methods that the final adapter will implement"""
    #_descriptor : Descriptor

    # def __init__(self) -> None:
    #     self._descriptor = descriptor

    def __init__(self) -> None:
        self._worker_logger = logging.getLogger(LoggerAlias.ADAPTER_WORKER.value)
        # Events
        self._event_callbacks: set[Callable[[AdapterEvent], None]] = set()

    @property
    @abstractmethod
    def descriptor(self) -> Descriptor:
        """Return the adapter descriptor"""

    @abstractmethod
    def _worker_read(self, fragment_timestamp: float) -> Fragment[DataT]: ...

    @abstractmethod
    def _worker_write(self, data: DataT) -> None: ...

    @abstractmethod
    def _worker_open(self) -> None:
        """Open the adapter, should raise a AdapterOpenError if the open failed"""

    @abstractmethod
    def _worker_close(self) -> None:
        if self.descriptor is not None:
            tracehub.emit_close(str(self.descriptor))
        self._worker_emit_event(AdapterClosedEvent())

    @abstractmethod
    def _selectable(self) -> HasFileno | None:
        """Return an object with fileno() that becomes readable when device data is available."""

    def _worker_emit_event(self, event: AdapterEvent) -> None:
        for callback in self._event_callbacks:
            try:
                callback(event)
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Never let user callback break worker
                self._worker_logger.exception(
                    "Adapter event callback failed with error : %s", str(e)
                )


# pylint: disable=too-many-instance-attributes
class AdapterWorker(Generic[DataT]):
    """Base Adapter worker"""

    _FRAME_BUFFER_MAX = 256
    _COMMAND_READY = b"\x00"

    def __init__(self, adapter_interface: AdapterWorkerInterface[DataT]) -> None:
        self._interface = adapter_interface
        self._worker_logger = logging.getLogger(LoggerAlias.ADAPTER_WORKER.value)

        # Frames
        self.frame_buffer: deque[ReadFrame[DataT]] = deque(maxlen=self._FRAME_BUFFER_MAX)
        self._next_frame_id = 0
        # Stop-conditions
        self._stop_conditions: list[StopCondition] = []

        # Timing
        self._last_write_timestamp: float | None = None
        self._timeout: ValidTimeoutType = None
        self._current_timeout: ValidTimeoutType = None

        # Adapter status
        self._opened = False
        self._first_opened = False

        # Command management
        self._pending_read: PendingRead[DataT] | None = None

        # Thread
        self._thread_running: bool = True
        self._command_queue_r, self._command_queue_w = socket.socketpair()
        self._command_queue_r.setblocking(False)
        self._command_queue_w.setblocking(False)
        self._command_queue: queue.Queue[ThreadCommand[Any]] = queue.Queue()
        self._worker_thread = threading.Thread(
            target=self._worker_thread_method, daemon=True
        )
        self._worker_thread.start()

    def next_frame_id(self) -> int:
        output = self._next_frame_id
        self._next_frame_id += 1
        return output

    def send_command(self, command: ThreadCommand[Any]) -> None:
        """Send command to the worker thread"""
        self._command_queue.put(command)
        # Wake up worker
        try:
            self._command_queue_w.send(self._COMMAND_READY)
        except OSError:
            # Worker may already be stopped
            pass

    @abstractmethod
    def _on_select_timeout(self, timestamp: float) -> None: ...

    @abstractmethod
    def _select_timeout(self) -> float | None: ...

    # pylint: disable=too-many-branches
    def _worker_thread_method(self) -> None:
        """
        Main worker thread loop (select-based reactor)

        - Always waits on:
            * command wakeup socket
            * device selectable (if any)
        - Also wakes up on the earliest deadline among:
            * stop-condition timeout (Continuation/Total)
            * pending read response deadline (before first qualifying fragment)
        """
        while self._thread_running:
            select_timeout = self._select_timeout()

            # Selectables
            selectables: list[HasFileno] = [self._command_queue_r]
            s = self._interface._selectable()  # pylint: disable=protected-access
            if s is not None:
                selectables.append(s)

            try:
                readable, _, _ = select(selectables, [], [], select_timeout)
                t = time.time()
            except ValueError:  # Negative file descriptor
                self._interface._worker_close()  # pylint: disable=protected-access
            else:
                # Manage command
                if self._command_queue_r in readable:
                    self._worker_drain_wakeup()
                    # Drain all commands currently queued
                    while True:
                        try:
                            cmd = self._command_queue.get(block=False)
                        except queue.Empty:
                            break
                        self._worker_manage_command(cmd)
                    continue

                if s is not None and s in readable:
                    # pylint: disable=protected-access
                    try:
                        frag = self._interface._worker_read(t)
                    except (AdapterDisconnected, AdapterReadError) as e:
                        if self._pending_read is not None:
                            self._pending_read.cmd.set_exception(e)
                            self._pending_read = None
                        self._interface._worker_close()
                    else:
                        self._worker_manage_fragment(frag)
                    continue

                # Timeout
                self._on_select_timeout(t)

    def _worker_drain_wakeup(self) -> None:
        # Drain all pending wakeup bytes (non-blocking)
        while True:
            try:
                _ = self._command_queue_r.recv(1024)
                if not _:
                    return
            except BlockingIOError:
                return
            except OSError:
                return

    def stop(self) -> None:
        """Stop the worker"""
        # This method is run by the worker thread, so to stop it we use the
        # thread_running attribute
        self._thread_running = False
        self._command_queue_r.close()
        self._command_queue_w.close()

    def _worker_check_descriptor(self) -> None:
        if (
            self._interface.descriptor is None
            or not self._interface.descriptor.is_initialized()
        ):
            raise AdapterOpenError("Descriptor not initialized")

    def _buffer_clear(self) -> None:
        self._interface._worker_emit_event(AdapterBufferEvent(
            added_frame_ids=[],
            removed_frame_ids=[frame.id for frame in self.frame_buffer]
        ))
        self.frame_buffer.clear()

    def _worker_manage_command(self, command: ThreadCommand[Any]) -> None:
        # pylint: disable=too-many-branches
        try:
            match command:
                case WriteCommand():
                    self._last_write_timestamp = time.time()
                    if self._interface.descriptor is None: # pylint: disable=protected-access
                        command.set_exception(AdapterWriteError("Missing descriptor"))
                    elif not self._opened:
                        command.set_exception(AdapterWriteError("Adapter is not opened"))
                    else:
                        tracehub.emit_write_frame(
                            str(self._interface.descriptor), command.frame
                        )
                        self._interface._worker_emit_event(AdapterWriteEvent(command.frame))
                        # pylint: disable=protected-access
                        self._interface._worker_write(command.frame.data)
                        command.set_result(None)
                case OpenCommand():
                    if self._opened:
                        self._worker_logger.warning("Adapter already opened")
                    else:
                        self._worker_check_descriptor()
                        try:
                            self._interface._worker_open()  # pylint: disable=protected-access
                        except AdapterOpenError as e:
                            self._opened = False
                            self._worker_logger.error(str(e))
                            command.set_exception(e)
                        else:
                            self._opened = True
                            if self._interface.descriptor is not None:
                                tracehub.emit_open(str(self._interface.descriptor))
                            # pylint: disable=protected-access 
                            self._interface._worker_emit_event(AdapterOpenedEvent())
                            self._first_opened = True
                            command.set_result(None)
                case CloseCommand():
                    self._interface._worker_close()  # pylint: disable=protected-access
                    self._opened = False
                    #self._worker_emit_event(AdapterClosedEvent())
                    self._buffer_clear()
                    # Cancel any pending read
                    if self._pending_read is not None:
                        self._pending_read.cmd.set_exception(AdapterDisconnected())
                        self._pending_read = None
                    command.set_result(None)
                case StopThreadCommand():
                    self.stop()
                    command.set_result(None)
                case FlushReadCommand():
                    self._buffer_clear()
                    command.set_result(None)
                case SetTimeoutCommand():
                    self._timeout = command.timeout
                    command.set_result(None)
                case IsOpenCommand():
                    command.set_result(self._opened)
                case AddEventCallbackCommand():
                    self._interface._event_callbacks.add(command.event_callback)
                    command.set_result(None)
                case ClearEventCallbacksCommand():
                    self._interface._event_callbacks.clear()
                    command.set_result(None)
                case ReadCommand():
                    self._worker_begin_read(command)
                case SetStopConditionsCommand():
                    self._stop_conditions = command.stop_conditions
                    command.set_result(None)
                case GetStopConditionsCommand():
                    command.set_result(self._stop_conditions)
                case _:
                    command.set_exception(
                        WorkerThreadError(f"Invalid command {command!r}")
                    )
        except Exception as e:  # pylint: disable=broad-exception-caught
            command.set_exception(e)

    def _worker_begin_read(self, cmd: ReadCommand[DataT]) -> None:
        """
        Register a pending read in the worker.

        - If scope is BUFFERED and we have buffered frames, complete immediately.
        - Otherwise store pending read and let the fragment/frame pipeline satisfy it.
        """
        t = time.time()

        if self._pending_read is not None:
            cmd.set_exception(
                WorkerThreadError("Concurrent read is not supported")
            )
            return
                    
        # Check if an element from the buffer should be poped
        if cmd.scope == ReadScope.BUFFERED:
            pop = True
        elif cmd.scope == ReadScope.LAST_WRITE:    
            if self._last_write_timestamp is None:
                cmd.set_exception(AdapterReadError("Cannot read with scope=LAST_WRITE without a previous write"))
                return
            pop = self.frame_buffer[0].first_fragment_timestamp >= self._last_write_timestamp

        # If the buffer is not empty, pop the first element (oldest one)
        if len(self.frame_buffer) > 0 and pop:
            frame = self.frame_buffer.popleft()
            self._interface._worker_emit_event(AdapterBufferEvent(
                added_frame_ids=[],
                removed_frame_ids=[frame.id]
            ))
            cmd.set_result(frame)
            return

        # Resolve timeout
        if cmd.timeout is ...:
            read_timeout = self._timeout
        elif cmd.timeout is None:
            read_timeout = None
        else:
            try:
                read_timeout = float(cmd.timeout)
            except (ValueError, TypeError) as e:
                raise RuntimeWarning("Invalid timeout : {cmd.timeout}") from e

        if read_timeout is None:
            raise RuntimeError("Cannot read without setting a timeout")

        response_deadline = None if read_timeout is None else (t + read_timeout)

        # Resolve stop-condition override (applied at next qualifying frame boundary)
        stop_override: list[StopCondition] | None = None
        if cmd.stop_conditions is not ...:
            if isinstance(cmd.stop_conditions, StopCondition):
                stop_override = [cmd.stop_conditions]
            elif isinstance(cmd.stop_conditions, list):
                stop_override = cmd.stop_conditions
            else:
                raise ValueError("Invalid stop_conditions override")

        self._pending_read = PendingRead(
            cmd=cmd,
            start_time=t,
            scope=cmd.scope,
            response_deadline=response_deadline,
            stop_override=stop_override,
        )

    @abstractmethod
    def _worker_manage_fragment(self, fragment: Fragment[DataT]) -> None: ...

    def _worker_deliver_frame(self, frame: ReadFrame[DataT]) -> None:
        """
        Route a completed frame:
        - complete pending read if it matches scope/time rules
        - else buffer it
        - always emit callback event (if configured)
        """
        self._interface._worker_emit_event(AdapterReadEvent(frame))
        if self._interface.descriptor is not None:
            tracehub.emit_read_frame(str(self._interface.descriptor), frame)

        pr = self._pending_read
        qualifies = False
        if pr is not None:
            if pr.scope == ReadScope.BUFFERED:
                qualifies = True
            elif pr.scope == ReadScope.NEXT:
                qualifies = frame.stop_timestamp > pr.start_time
            elif pr.scope == ReadScope.LAST_WRITE:
                if self._last_write_timestamp is not None:
                    # The opposite should technically never happen because we check when the
                    # ReadCommand is received
                    qualifies = frame.stop_timestamp > self._last_write_timestamp

            if qualifies:
                # Restore stop conditions if we had applied an override
                pr.cmd.set_result(frame)
                self._pending_read = None
                return

        # Not consumed by a pending read => buffer it
        self.frame_buffer.append(frame)
        self._interface._worker_emit_event(AdapterBufferEvent(
            added_frame_ids=[frame.id],
            removed_frame_ids=[]
        ))


    def _worker_fail_pending_read_timeout(self) -> None:
        """
        Called when the pending read response timeout expires BEFORE a qualifying first fragment.
        """
        pr = self._pending_read
        if pr is None:
            return

        # Resolve timeout again the same way as begin_read  did
        cmd = pr.cmd
        if cmd.timeout is ...:
            read_timeout = self._timeout
        elif cmd.timeout is None:
            read_timeout = None
        else:
            try:
                read_timeout = float(cmd.timeout)
            except (ValueError, TypeError) as e:
                raise RuntimeError(f"Invalid timeout : {cmd.timeout}") from e

        if read_timeout is None:
            pr.cmd.set_exception(AdapterReadError("Read timeout configuration invalid"))
            self._pending_read = None
            return

        pr.cmd.set_exception(
            AdapterTimeoutError(
                float("nan") if read_timeout is None else read_timeout
            )
        )
        self._pending_read = None
