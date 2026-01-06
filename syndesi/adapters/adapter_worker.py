# File : adapter_worker.py
# Author : Sébastien Deriaz
# License : GPL

"""
Adapter worker mixin and worker command types.
"""

import logging
import queue
import socket
import time
from abc import abstractmethod
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from select import select
from types import EllipsisType
from typing import Any, Protocol

from syndesi.tools.log_settings import LoggerAlias

from ..component import AdapterFrame, Descriptor, Event, ReadScope, ThreadCommand
from ..tools.errors import (
    AdapterDisconnected,
    AdapterError,
    AdapterOpenError,
    AdapterReadError,
    AdapterTimeoutError,
    AdapterWriteError,
    WorkerThreadError,
)
from .stop_conditions import (
    Continuation,
    Fragment,
    StopCondition,
    StopConditionType,
    Total,
)
from .timeout import Timeout, TimeoutAction, any_to_timeout


def nmin(a: float | None, b: float | None) -> float | None:
    """
    Return min of a and b, ignoring None values

    If both a and b are None, return None
    """
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


class HasFileno(Protocol):
    """
    A class to annotate objects that have a fileno function
    """

    def fileno(self) -> int:
        """
        Return file number
        """
        return -1


# ┌────────────────┐
# │ Adapter events │
# └────────────────┘


class AdapterEvent(Event):
    """Adapter event"""


class AdapterDisconnectedEvent(AdapterEvent):
    """Adapter disconnected event"""


@dataclass
class AdapterFrameEvent(AdapterEvent):
    """Adapter frame event, emitted when new data is available"""

    frame: AdapterFrame


@dataclass
class FirstFragmentEvent(AdapterEvent):
    """Adapter first fragment event"""

    timestamp: float
    next_timeout_timestamp: float | None


# ┌───────────────────────────────┐
# │ Worker commands (composition) │
# └───────────────────────────────┘


class OpenCommand(ThreadCommand[None]):
    """Open the adapter"""


class CloseCommand(ThreadCommand[None]):
    """Close the adapter"""


class StopThreadCommand(ThreadCommand[None]):
    """Stop the worker thread"""


class FlushReadCommand(ThreadCommand[None]):
    """Clear buffered frames and reset worker read state"""


class SetEventCallbackCommand(ThreadCommand[None]):
    """Configure the callback event"""

    def __init__(self, callback: Callable[[AdapterEvent], None] | None) -> None:
        super().__init__()
        self.event_callback = callback


class WriteCommand(ThreadCommand[None]):
    """Write data to the adapter"""

    def __init__(self, data: bytes) -> None:
        super().__init__()
        self.data = data


class SetStopConditionsCommand(ThreadCommand[None]):
    """Configure adapter stop conditions"""

    def __init__(self, stop_conditions: list[StopCondition]) -> None:
        super().__init__()
        self.stop_conditions = stop_conditions


class SetTimeoutCommand(ThreadCommand[None]):
    """Configure adapter timeout"""

    def __init__(self, timeout: Timeout) -> None:
        super().__init__()
        self.timeout = timeout


class IsOpenCommand(ThreadCommand[bool]):
    """Return True if the adapter is opened"""


class ReadCommand(ThreadCommand[AdapterFrame]):
    """
    Read a frame (detailed) from the adapter.

    timeout:
        - ... => use adapter default timeout
        - None => wait indefinitely for first fragment (response timeout disabled)
        - Timeout => as provided

    stop_conditions:
        - ... => use current worker stop conditions
        - StopCondition/list => override for the *next* frame that satisfies this read
                               (applied at frame boundary; not mid-frame)
    """

    def __init__(
        self,
        timeout: Timeout | EllipsisType | None,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition],
        scope: ReadScope,
    ) -> None:
        super().__init__()
        self.timeout = timeout
        self.stop_conditions = stop_conditions
        self.scope = scope


class SetDescriptorCommand(ThreadCommand[None]):
    """
    Command to configure the worker descriptor (sync with the adapter subclass descriptor)
    """

    def __init__(self, descriptor: Descriptor) -> None:
        super().__init__()
        self.descriptor = descriptor


# pylint: disable=too-many-instance-attributes
class _PendingRead:
    """
    Worker-thread state for one outstanding read.
    """

    __slots__ = (
        "cmd",
        "start_time",
        "response_deadline",
        "first_fragment_seen",
        "scope",
        "stop_override",
        "stop_override_applied",
        "prev_stop_conditions",
    )

    def __init__(
        self,
        *,
        cmd: ReadCommand,
        start_time: float,
        response_deadline: float | None,
        scope: ReadScope,
        stop_override: list[StopCondition] | None,
    ) -> None:
        self.cmd = cmd
        self.start_time = start_time
        self.response_deadline = (
            response_deadline  # only used before qualifying first fragment
        )
        self.first_fragment_seen = False
        self.scope = scope

        self.stop_override = stop_override
        self.stop_override_applied = False
        self.prev_stop_conditions: list[StopCondition] | None = None


# pylint: disable=too-many-instance-attributes
class AdapterWorker:
    """
    Adapter worker
    """

    # How many completed frames we keep for BUFFERED reads
    _FRAME_BUFFER_MAX = 256
    _COMMAND_READY = b"\x00"

    def __init__(self) -> None:
        # Command queue (worker input)
        self._command_queue_r, self._command_queue_w = socket.socketpair()
        self._command_queue_r.setblocking(False)
        self._command_queue_w.setblocking(False)

        self._command_queue: queue.Queue[ThreadCommand[Any]] = queue.Queue()

        self._frame_buffer: deque[AdapterFrame] = deque(maxlen=self._FRAME_BUFFER_MAX)

        self._worker_descriptor: Descriptor | None = None

        self._pending_read: _PendingRead | None = None

        self._timeout: Timeout | None = None

        self._worker_logger = logging.getLogger(LoggerAlias.ADAPTER_WORKER.value)

        self._stop_conditions: list[StopCondition] = []

        # Worker lifecycle and state
        self._thread_running = True
        self._opened = False
        self._first_opened = False

        # Fragment assembly state
        self._first_fragment: bool = True
        self.fragments: list[Fragment] = []
        self._previous_buffer = Fragment(b"", time.time())
        self._first_fragment_timestamp: float | None = None
        self._last_fragment_timestamp: float | None = None
        self._last_write_timestamp: float | None = None
        self._timeout_origin: StopConditionType | None = None
        self._next_stop_condition_timeout_timestamp: float | None = None
        self._read_start_timestamp: float | None = None

        self._event_callback: Callable[[AdapterEvent], None] | None = None

    # ┌─────────────────┐
    # │ Worker plumbing │
    # └─────────────────┘

    def _worker_send_command(self, command: ThreadCommand[Any]) -> None:
        self._command_queue.put(command)
        # Wake up worker
        try:
            self._command_queue_w.send(self._COMMAND_READY)
        except OSError:
            # Worker may already be stopped
            pass

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

    def _worker_check_descriptor(self) -> None:
        if (
            self._worker_descriptor is None
            or not self._worker_descriptor.is_initialized()
        ):
            raise AdapterOpenError("Descriptor not initialized")

    # Abstract worker methods, to be implemented in the adapter subclasses
    @abstractmethod
    def _selectable(self) -> HasFileno | None:
        """Return an object with fileno() that becomes readable when device data is available."""

    @abstractmethod
    def _worker_read(self, fragment_timestamp: float) -> Fragment:
        """Read one fragment from the low-level layer and return it."""

    @abstractmethod
    def _worker_write(self, data: bytes) -> None:
        if not self._opened and not self._first_opened:
            self._worker_open()
            if not self._opened:
                raise AdapterWriteError("Adapter not opened")

    @abstractmethod
    def _worker_open(self) -> None: ...

    @abstractmethod
    def _worker_close(self) -> None: ...

    # ┌──────────────────────────┐
    # │ Worker: command handling │
    # └──────────────────────────┘

    def _worker_manage_command(self, command: ThreadCommand[Any]) -> None:
        # pylint: disable=too-many-branches
        try:
            match command:
                case WriteCommand():
                    self._last_write_timestamp = time.time()
                    self._worker_write(command.data)
                    command.set_result(None)
                case OpenCommand():
                    self._worker_open()
                    self._opened = True
                    self._first_opened = True
                    command.set_result(None)
                case CloseCommand():
                    self._worker_close()
                    self._opened = False
                    # Closing should also reset read assembly
                    self._worker_reset_read()
                    self._frame_buffer.clear()
                    # Cancel any pending read
                    if self._pending_read is not None:
                        self._pending_read.cmd.set_exception(AdapterDisconnected())
                        self._pending_read = None
                    command.set_result(None)
                case StopThreadCommand():
                    self._thread_running = False
                    command.set_result(None)
                case FlushReadCommand():
                    self._frame_buffer.clear()
                    self._worker_reset_read()
                    command.set_result(None)
                case SetStopConditionsCommand():
                    self._stop_conditions = command.stop_conditions
                    command.set_result(None)
                case SetTimeoutCommand():
                    self._timeout = command.timeout
                    command.set_result(None)
                case IsOpenCommand():
                    command.set_result(self._opened)
                case SetEventCallbackCommand():
                    self._event_callback = command.event_callback
                    command.set_result(None)
                case ReadCommand():
                    self._worker_begin_read(command)
                case SetDescriptorCommand():
                    self._worker_descriptor = command.descriptor
                    command.set_result(None)
                case _:
                    command.set_exception(
                        WorkerThreadError(f"Invalid command {command!r}")
                    )
        except AdapterError as e:
            command.set_exception(e)
        except Exception as e:  # pylint: disable=broad-exception-caught
            command.set_exception(WorkerThreadError(str(e)))

    def _worker_begin_read(self, cmd: ReadCommand) -> None:
        """
        Register a pending read in the worker.

        - If scope is BUFFERED and we have buffered frames, complete immediately.
        - Otherwise store pending read and let the fragment/frame pipeline satisfy it.
        """
        if self._pending_read is not None:
            cmd.set_exception(
                WorkerThreadError("Concurrent read_detailed is not supported")
            )
            return

        # If buffered scope, serve immediately from buffer if available
        if cmd.scope == ReadScope.BUFFERED and len(self._frame_buffer) > 0:
            frame = self._frame_buffer.popleft()
            cmd.set_result(frame)
            return

        start = time.time()

        # Resolve timeout
        if cmd.timeout is ...:
            read_timeout = self._timeout
        elif cmd.timeout is None:
            read_timeout = Timeout(response=None)
        elif isinstance(cmd.timeout, Timeout):
            read_timeout = cmd.timeout
        else:
            read_timeout = any_to_timeout(cmd.timeout)

        if read_timeout is None:
            raise RuntimeError("Cannot read without setting a timeout")
        if not read_timeout.is_initialized():
            raise RuntimeError("Timeout needs to be initialized")

        resp = read_timeout.response()
        response_deadline = None if resp is None else (start + resp)

        # Resolve stop-condition override (applied at next qualifying frame boundary)
        stop_override: list[StopCondition] | None = None
        if cmd.stop_conditions is not ...:
            if isinstance(cmd.stop_conditions, StopCondition):
                stop_override = [cmd.stop_conditions]
            elif isinstance(cmd.stop_conditions, list):
                stop_override = cmd.stop_conditions
            else:
                raise ValueError("Invalid stop_conditions override")

        self._pending_read = _PendingRead(
            cmd=cmd,
            start_time=start,
            response_deadline=response_deadline,
            scope=cmd.scope,
            stop_override=stop_override,
        )

    # ┌────────────────────────┐
    # │ Worker: event emission │
    # └────────────────────────┘

    def _worker_emit_event(self, event: AdapterEvent) -> None:
        if self._event_callback is not None:
            try:
                self._event_callback(event)
            except Exception as e:  # pylint: disable=broad-exception-caught
                # Never let user callback break worker
                self._worker_logger.exception(
                    "Adapter event callback failed with error : %s", str(e)
                )

    def _worker_deliver_frame(self, frame: AdapterFrame) -> None:
        """
        Route a completed frame:
        - complete pending read if it matches scope/time rules
        - else buffer it
        - always emit callback event (if configured)
        """
        self._worker_emit_event(AdapterFrameEvent(frame))

        pr = self._pending_read
        if pr is not None:
            first_ts = frame.fragments[0].timestamp if frame.fragments else float("nan")
            qualifies = (first_ts > pr.start_time) or (pr.scope == ReadScope.BUFFERED)
            if qualifies:
                # Restore stop conditions if we had applied an override
                if pr.stop_override_applied and pr.prev_stop_conditions is not None:
                    self._stop_conditions = pr.prev_stop_conditions

                pr.cmd.set_result(frame)
                self._pending_read = None
                return

        # Not consumed by a pending read => buffer it
        self._frame_buffer.append(frame)

    def _worker_fail_pending_read_timeout(self) -> None:
        """
        Called when the pending read response timeout expires BEFORE a qualifying first fragment.
        """
        pr = self._pending_read
        if pr is None:
            return

        # Resolve timeout again the same way as begin_read did
        cmd = pr.cmd
        if cmd.timeout is ...:
            read_timeout = self._timeout
        elif cmd.timeout is None:
            read_timeout = Timeout(response=None)
        elif isinstance(cmd.timeout, Timeout):
            read_timeout = cmd.timeout
        else:
            read_timeout = any_to_timeout(cmd.timeout)

        if read_timeout is None:
            pr.cmd.set_exception(AdapterReadError("Read timeout configuration invalid"))
            self._pending_read = None
            return

        match read_timeout.action:
            case TimeoutAction.RETURN_EMPTY:
                pr.cmd.set_result(
                    AdapterFrame(
                        fragments=[Fragment(b"", time.time())],
                        stop_timestamp=None,
                        stop_condition_type=None,
                        previous_read_buffer_used=False,
                        response_delay=None,
                    )
                )
                self._pending_read = None
            case TimeoutAction.ERROR:
                timeout_value = read_timeout.response()
                pr.cmd.set_exception(
                    AdapterTimeoutError(
                        float("nan") if timeout_value is None else timeout_value
                    )
                )
                self._pending_read = None
            case _:
                pr.cmd.set_exception(NotImplementedError())
                self._pending_read = None

    # ┌──────────────────────────────┐
    # │ Worker: fragment/frame logic │
    # └──────────────────────────────┘

    def _worker_on_first_fragment(self, fragment: Fragment) -> None:
        """
        Called at frame boundary (first fragment of a new frame).
        Used to:
        - mark the pending read as having seen a qualifying first fragment
        (disables response timeout)
        - apply stop-condition overrides at frame boundary (not mid-frame)
        """
        pr = self._pending_read
        if pr is None:
            return

        qualifies = (fragment.timestamp > pr.start_time) or (
            pr.scope == ReadScope.BUFFERED
        )
        if not qualifies:
            return

        pr.first_fragment_seen = True
        pr.response_deadline = (
            None  # disable response timeout once we have a qualifying first fragment
        )

        if pr.stop_override is not None and not pr.stop_override_applied:
            pr.prev_stop_conditions = self._stop_conditions
            self._stop_conditions = pr.stop_override
            pr.stop_override_applied = True

    def _worker_manage_fragment(self, fragment: Fragment) -> None:
        # pylint: disable=too-many-branches, too-many-statements
        self._last_fragment_timestamp = fragment.timestamp

        if self._last_write_timestamp is not None:
            write_delta = fragment.timestamp - self._last_write_timestamp
            initiate_timestamp = fragment.timestamp
        else:
            write_delta = float("nan")
            initiate_timestamp = time.time()

        if fragment.data == b"":
            # Disconnected / EOF
            try:
                self._worker_close()
            except AdapterError:
                pass
            self._opened = False
            self._worker_emit_event(AdapterDisconnectedEvent())

            # Fail any pending read
            if self._pending_read is not None:
                self._pending_read.cmd.set_exception(AdapterDisconnected())
                # Restore stop conditions if overridden
                if (
                    self._pending_read.stop_override_applied
                    and self._pending_read.prev_stop_conditions is not None
                ):
                    self._stop_conditions = self._pending_read.prev_stop_conditions
                self._pending_read = None
            return

        suffix = " (first)" if self._first_fragment else ""
        self._worker_logger.debug(
            "New fragment %+.3f %s%s", write_delta, fragment, suffix
        )

        stop_timestamp = float("nan")
        kept = fragment

        while True:
            if self._first_fragment:
                self._first_fragment = False
                self._read_start_timestamp = fragment.timestamp
                self._first_fragment_timestamp = fragment.timestamp

                # Notify pending read (and apply stop override at boundary)
                self._worker_on_first_fragment(fragment)

                for stop_condition in self._stop_conditions:
                    stop_condition.initiate_read(initiate_timestamp)

            stop = False
            stop_condition_type: StopConditionType | None = None

            for stop_condition in self._stop_conditions:
                (
                    stop,
                    kept,
                    self._previous_buffer,
                    next_stop_condition_timeout_timestamp,
                ) = stop_condition.evaluate(kept)

                self._next_stop_condition_timeout_timestamp = nmin(
                    next_stop_condition_timeout_timestamp,
                    self._next_stop_condition_timeout_timestamp,
                )
                if stop:
                    stop_condition_type = stop_condition.type()
                    stop_timestamp = kept.timestamp
                    break

            self.fragments.append(kept)

            if stop_condition_type is None:
                break

            # frame complete
            self._first_fragment = True

            if self._last_write_timestamp is None:
                response_delay = None
            else:
                response_delay = (
                    self.fragments[0].timestamp - self._last_write_timestamp
                )

            frame = AdapterFrame(
                fragments=self.fragments,
                stop_timestamp=stop_timestamp,
                stop_condition_type=stop_condition_type,
                previous_read_buffer_used=False,
                response_delay=response_delay,
            )
            self._worker_logger.debug(
                "Frame %s (%s)",
                "+".join(repr(f.data) for f in self.fragments),
                stop_condition_type.value if stop_condition_type is not None else "---",
            )

            self._worker_deliver_frame(frame)

            # Reset for next frame
            self._next_stop_condition_timeout_timestamp = None
            self.fragments = []

            if len(self._previous_buffer.data) > 0:
                kept = self._previous_buffer
            else:
                break

    def _worker_on_stop_condition_timeout(self, timestamp: float) -> None:
        """
        Called when a stop-condition timeout expires (Continuation/Total),
        producing a frame if we have accumulated fragments.
        """
        if len(self.fragments) > 0:
            if self._last_write_timestamp is None:
                response_delay = None
            else:
                response_delay = (
                    self.fragments[0].timestamp - self._last_write_timestamp
                )

            frame = AdapterFrame(
                fragments=self.fragments,
                stop_timestamp=timestamp,
                stop_condition_type=self._timeout_origin,
                previous_read_buffer_used=False,
                response_delay=response_delay,
            )
            self._worker_deliver_frame(frame)

        self._worker_reset_read()

    def _worker_reset_read(self) -> None:
        self._last_fragment_timestamp = None
        self._first_fragment_timestamp = None
        self._first_fragment = True
        self._last_write_timestamp = None
        self.fragments = []
        self._next_stop_condition_timeout_timestamp = None
        self._timeout_origin = None

    def _worker_next_timeout_timestamp(self) -> float | None:
        stop_conditions = self._stop_conditions
        next_timestamp = None

        for stop_condition in stop_conditions:
            if isinstance(stop_condition, Continuation):
                if self._last_fragment_timestamp is not None:
                    next_timestamp = nmin(
                        next_timestamp,
                        self._last_fragment_timestamp + stop_condition.continuation,
                    )
                    self._timeout_origin = stop_condition.type()
            elif isinstance(stop_condition, Total):
                if self._first_fragment_timestamp is not None:
                    next_timestamp = nmin(
                        next_timestamp,
                        self._first_fragment_timestamp + stop_condition.total,
                    )
                    self._timeout_origin = stop_condition.type()

        return next_timestamp

    # ┌───────────────────┐
    # │ Worker: main loop │
    # └───────────────────┘

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
            now = time.time()

            # Refresh next stop-condition timeout from current fragment state
            self._next_stop_condition_timeout_timestamp = (
                self._worker_next_timeout_timestamp()
            )

            # Compute pending read response deadline (only before first qualifying fragment)
            pr_deadline = None
            if (
                self._pending_read is not None
                and not self._pending_read.first_fragment_seen
            ):
                pr_deadline = self._pending_read.response_deadline

            # Earliest deadline wins
            deadline = nmin(self._next_stop_condition_timeout_timestamp, pr_deadline)
            if deadline is None:
                select_timeout = None
            else:
                select_timeout = max(0.0, deadline - now)

            # Selectables
            selectables: list[HasFileno] = [self._command_queue_r]
            s = self._selectable()
            if s is not None:
                selectables.append(s)

            readable, _, _ = select(selectables, [], [], select_timeout)
            t = time.time()

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
                if not self._opened and not self._first_opened:
                    self._worker_open()
                    if not self._opened:
                        raise AdapterReadError("Adapter not opened")

                frag = self._worker_read(t)
                self._worker_manage_fragment(frag)
                continue

            # Timeout wakeup: decide what timed out
            # 1) pending read response timeout (before qualifying first fragment)
            if (
                self._pending_read is not None
                and not self._pending_read.first_fragment_seen
            ):
                dl = self._pending_read.response_deadline
                if dl is not None and t >= dl:
                    self._worker_fail_pending_read_timeout()
                    # do NOT return; stop-condition timeout might also be due

            # 2) stop-condition timeout (Continuation/Total)
            if (
                self._next_stop_condition_timeout_timestamp is not None
                and t >= self._next_stop_condition_timeout_timestamp
            ):
                self._worker_on_stop_condition_timeout(t)
