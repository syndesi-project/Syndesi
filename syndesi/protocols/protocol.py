# File : protocol.py
# Author : Sébastien Deriaz
# License : GPL
"""
Protocols, the endpoints that turn the frames of an adapter into payloads

A protocol is built exactly like an adapter, one level up : a ProtocolBackend holds
what is specific to the protocol, a ProtocolEngine drives it and exposes futures, and
the two facades only wait for those futures

    Adapter   :  AdapterBackend (I/O)  + Framer          -> AdapterEngine
    Protocol  :  ProtocolBackend (assembly + encoding)   -> ProtocolEngine

The adapter layer splits I/O from assembly because one is impure and the other is pure.
A protocol has no I/O at all, its adapter is its I/O, so assembly and encoding live in
a single class

    Delimited ──contains──▶ ProtocolEngine ──feeds on──▶ AdapterEngine ◀──contains── IP
                └ DelimitedBackend                            │
                       ▲───────────── frames ─────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
import weakref
from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Generic, Self, TypeVar

from ..adapters.adapter import Adapter, AsyncAdapter
from ..adapters.engine import (
    AdapterEngine,
    ClearBufferCommand,
    Command,
    ReadScope,
)
from ..adapters.reactor import default_reactor
from ..adapters.events import AdapterEvent
from ..adapters.framer import AdapterReadFrame
from ..adapters.stop_conditions import StopCondition
from ..adapters.utils import HasFileno, TimeoutParameterType, TimeoutType, nmin
from ..tools.errors import (
    AdapterTimeoutError,
    ProtocolReadError,
    ProtocolWriteError,
    WorkerThreadError,
)
from ..tools.log_settings import LoggerAlias

AdapterT = TypeVar("AdapterT")
ProtocolT = TypeVar("ProtocolT")


# ┌────────┐
# │ Frames │
# └────────┘


@dataclass(kw_only=True)
class ProtocolFrame(Generic[ProtocolT]):
    """A payload assembled by a protocol, as returned to the user"""

    data: ProtocolT
    id: int
    response_delay: float = float("nan")

    def __str__(self) -> str:
        return f"ProtocolFrame({self.data!r})"


@dataclass
class BackendOutput(Generic[AdapterT, ProtocolT]):
    """
    What a ProtocolBackend produces from one adapter frame, or from one deadline

    payloads is empty while the protocol frame is still incomplete, and holds more than
    one when a single adapter frame completes several. writes are emitted before the
    payloads are delivered, which is what lets a backend acknowledge or retry
    """

    payloads: list[ProtocolT] = field(default_factory=list)
    writes: list[AdapterT] = field(default_factory=list)


# ┌─────────┐
# │ Backend │
# └─────────┘


class ProtocolBackend(Generic[AdapterT, ProtocolT], ABC):
    """
    Everything specific to one protocol : how payloads are encoded, and how the frames
    of an adapter are assembled into them

    Pure : no socket, no thread, no future. Every method runs on the reactor thread, so
    the backend can keep whatever state it needs (the last payload written, the
    transactions in flight, a state machine) without any locking

    Assembling several adapter frames into one payload is the normal case : return an
    empty BackendOutput until the payload is complete. A frame that doesn't belong to
    what is being waited for (an acknowledgement, another transaction) is dropped the
    same way, by returning nothing for it
    """

    @abstractmethod
    def encode(self, payload: ProtocolT) -> list[AdapterT]:
        """
        Turn a payload into the data written to the adapter, possibly in several writes

        Runs on the reactor thread, ordered with push() : this is where a backend
        records what it has just sent if it needs it to match the answer
        """

    @abstractmethod
    def push(
        self, frame: AdapterReadFrame[AdapterT]
    ) -> BackendOutput[AdapterT, ProtocolT]:
        """Take one adapter frame and return what it completes, if anything"""

    def next_deadline(self) -> float | None:
        """
        Timestamp at which on_deadline must be called, None if the backend isn't
        waiting for one. Used by a protocol whose frame ends on a delay
        """
        return None

    def on_deadline(self, now: float) -> BackendOutput[AdapterT, ProtocolT]:
        """Called when the timestamp returned by next_deadline is reached"""
        del now  # a backend that overrides this one uses it
        return BackendOutput()

    @property
    def in_progress(self) -> bool:
        """True while a payload is being assembled"""
        return False

    def reset(self) -> None:
        """Discard the payload being assembled, called by clear_buffer"""

    @property
    def stop_conditions(self) -> list[StopCondition] | None:
        """
        Framing the adapter must use, None to leave it alone

        Read once, when the protocol is built. It cannot be changed frame by frame : a
        single read from the transport can complete several frames at once, so a new
        framing decided from frame n would always arrive after frame n+1 was cut. A
        protocol whose framing is self describing (a length field, a binary block)
        takes FragmentSC() here and assembles the bytes itself in push()
        """
        return None

    @property
    def default_timeout(self) -> TimeoutType:
        """Time to wait for a complete protocol frame, when none was given"""
        return None

    @property
    def adapter_default_timeout(self) -> TimeoutParameterType:
        """
        Time the adapter waits for the first fragment, ``...`` to leave it alone

        Only applied if the user didn't set the adapter timeout themselves
        """
        return ...


# ┌──────────┐
# │ Commands │
# └──────────┘


class ProtocolWriteCommand(Generic[ProtocolT], Command[None]):
    """Encode a payload and write it to the adapter"""

    def __init__(self, payload: ProtocolT) -> None:
        super().__init__()
        self.payload = payload


class ConfigureBackendCommand(Command[None]):
    """Run an action on the backend, on the reactor thread"""

    def __init__(self, action: Callable[[Any], None]) -> None:
        super().__init__()
        self.action = action


class ProtocolWriteRawCommand(Generic[AdapterT], Command[None]):
    """Write data to the adapter without encoding it"""

    def __init__(self, data: AdapterT) -> None:
        super().__init__()
        self.data = data


class ProtocolReadCommand(Generic[ProtocolT], Command[ProtocolFrame[ProtocolT]]):
    """Read one protocol frame"""

    def __init__(self, timeout: TimeoutParameterType, scope: ReadScope) -> None:
        super().__init__()
        self.timeout = timeout
        self.scope = scope


class ProtocolStopCommand(Command[None]):
    """Detach the protocol engine from the reactor and give the stream back"""


class SetProtocolTimeoutCommand(Command[None]):
    """Set the protocol timeout"""

    def __init__(self, timeout: TimeoutType) -> None:
        super().__init__()
        self.timeout = timeout


@dataclass
class PendingProtocolRead(Generic[ProtocolT]):
    """The single outstanding protocol read"""

    command: ProtocolReadCommand[ProtocolT]
    start_time: float
    scope: ReadScope
    response_deadline: float | None
    timeout: TimeoutType


# ┌────────┐
# │ Engine │
# └────────┘


# pylint: disable=too-many-instance-attributes
class ProtocolEngine(Generic[AdapterT, ProtocolT]):
    """
    Drives one ProtocolBackend on the reactor thread and exposes it as futures

    A reactor client like an adapter engine, with one difference : it has no selectable.
    Instead of being woken by select(), it is fed by the adapter engine whose frame
    stream it owns. Everything else is the same shape : one pending read, a frame
    buffer, deadlines

    Parameters
    ----------
    adapter_engine : AdapterEngine
    backend : ProtocolBackend
    timeout : float, None or ...
        ``...`` for the backend default
    alias : str
    """

    _FRAME_BUFFER_MAX = 256

    def __init__(
        self,
        adapter_engine: AdapterEngine[Any, AdapterT],
        backend: ProtocolBackend[AdapterT, ProtocolT],
        *,
        timeout: TimeoutParameterType = ...,
        alias: str = "",
    ) -> None:
        self._adapter_engine = adapter_engine
        self._backend = backend
        self._timeout = backend.default_timeout if timeout is ... else timeout
        self.alias = alias
        self._logger = logging.getLogger(LoggerAlias.ENGINE.value)

        self._commands: queue.SimpleQueue[Command[Any]] = queue.SimpleQueue()
        self._callbacks: list[Callable[[AdapterEvent], None]] = []
        # Frames and failures, in the order they happened : a frame that couldn't be
        # decoded must fail the read that would have received it, not whichever one
        # happened to be waiting when it arrived
        self.frame_buffer: deque[ProtocolFrame[ProtocolT] | BaseException] = deque(
            maxlen=self._FRAME_BUFFER_MAX
        )
        self._frame_id = 0
        self._pending_read: PendingProtocolRead[ProtocolT] | None = None
        self._last_write_timestamp: float | None = None
        # first_fragment_timestamp of the first adapter frame of the payload being
        # assembled, the only thing needed to date a payload made of several frames
        self._assembly_start: float | None = None

        self._reactor = default_reactor()
        self._reactor.attach(self)

        # Takes ownership of the frame stream, and imposes the framing the backend needs.
        # Submitted here, waited for by the sync facade only : the adapter engine runs its
        # commands in order, so it applies before any later operation either way
        self._configuration: list[Future[None]] = [adapter_engine.set_frame_sink(self)]

        stop_conditions = backend.stop_conditions
        if stop_conditions is not None:
            self._configuration.append(
                adapter_engine.set_stop_conditions(stop_conditions)
            )

    # ┌────────────────────────────────┐
    # │ User interface, returns futures │
    # └────────────────────────────────┘

    @property
    def configuration(self) -> list[Future[None]]:
        """
        What was submitted to the adapter when this engine was built

        The sync facade waits for these, so that the adapter attributes are up to date
        right after the constructor returns
        """
        return self._configuration

    @property
    def is_open(self) -> bool:
        """True if the adapter is open"""
        return self._adapter_engine.is_open

    @property
    def timeout(self) -> TimeoutType:
        """Time to wait for a complete protocol frame"""
        return self._timeout

    def open(self) -> Future[None]:
        """Open the adapter"""
        return self._adapter_engine.open()

    def close(self) -> Future[None]:
        """Close the adapter"""
        return self._adapter_engine.close()

    def write(self, payload: ProtocolT) -> ProtocolWriteCommand[ProtocolT]:
        """Encode a payload and write it"""
        return self._submit(ProtocolWriteCommand(payload))

    def configure(self, action: Callable[[Any], None]) -> ConfigureBackendCommand:
        """
        Reconfigure the backend from another thread

        The backend runs on the reactor thread, so changing one of its attributes from
        the caller's thread would race with a push() or an encode(). The action is run
        there instead, and the adapter framing follows : a backend that answers a new
        set of stop-conditions gets them applied right after
        """
        return self._submit(ConfigureBackendCommand(action))

    def write_raw(self, data: AdapterT) -> ProtocolWriteRawCommand[AdapterT]:
        """
        Write data to the adapter without encoding it

        Goes through the engine rather than straight to the adapter, so that the write
        timestamp is recorded and a following LAST_WRITE read still works
        """
        return self._submit(ProtocolWriteRawCommand(data))

    def read(
        self,
        timeout: TimeoutParameterType = ...,
        scope: ReadScope = ReadScope.BUFFERED,
    ) -> ProtocolReadCommand[ProtocolT]:
        """Read one protocol frame"""
        return self._submit(ProtocolReadCommand(timeout, scope))

    def set_timeout(self, timeout: TimeoutType) -> SetProtocolTimeoutCommand:
        """Set the time to wait for a complete protocol frame"""
        return self._submit(SetProtocolTimeoutCommand(timeout))

    def clear_buffer(self) -> ClearBufferCommand:
        """
        Drop the buffered payloads and the one being assembled, down to the adapter

        Propagated : clearing asks for a clean slate, bytes left from the previous
        exchange would otherwise come back on the next read
        """
        self._submit(_ClearProtocolBufferCommand())
        return self._adapter_engine.clear_buffer()

    def register_event_callback(
        self, callback: Callable[[AdapterEvent], None]
    ) -> Future[None]:
        """Register an adapter event callback"""
        return self._adapter_engine.register_event_callback(callback)

    def clear_event_callbacks(self) -> Future[None]:
        """Remove every adapter event callback"""
        return self._adapter_engine.clear_event_callbacks()

    def stop(self) -> ProtocolStopCommand:
        """Give the frame stream back to the adapter and leave the reactor"""
        self._adapter_engine.set_frame_sink(None)
        return self._submit(ProtocolStopCommand())

    def _submit(self, command: CommandT) -> CommandT:
        self._commands.put(command)
        self._reactor.wakeup()
        return command

    # ┌───────────────────┐
    # │ Reactor interface │
    # └───────────────────┘

    def selectable(self) -> HasFileno | None:
        """None : this engine is fed by the adapter engine, not by select()"""
        return None

    def on_readable(self, now: float) -> None:
        """Never called, the reactor only watches clients with a selectable"""

    def next_deadline(self) -> float | None:
        """Earliest timestamp at which on_deadline must be called"""
        deadline = self._backend.next_deadline()
        pending = self._pending_read
        if pending is not None:
            deadline = nmin(deadline, pending.response_deadline)
        return deadline

    def on_deadline(self, now: float) -> None:
        """A deadline returned by next_deadline has been reached"""
        self._emit_output(self._backend.on_deadline(now))

        pending = self._pending_read
        if (
            pending is not None
            and pending.response_deadline is not None
            and now >= pending.response_deadline
        ):
            self._pending_read = None
            self._adapter_engine.arm_fragment_deadline(None)
            self._fail(
                pending.command,
                AdapterTimeoutError(
                    float("nan") if pending.timeout is None else pending.timeout
                ),
            )

    def drain_commands(self) -> None:
        """Run every queued command"""
        self._drop_cancelled_read()
        while True:
            try:
                command = self._commands.get(block=False)
            except queue.Empty:
                return
            if not isinstance(command, ProtocolReadCommand) and not self._claim(command):
                continue
            try:
                self._execute(command)
            except Exception as e:  # pylint: disable=broad-exception-caught
                self._fail(command, e)

    # ┌──────────────────────┐
    # │ Frame sink interface │
    # └──────────────────────┘

    def on_frame(self, frame: AdapterReadFrame[AdapterT]) -> None:
        """An adapter frame has been assembled, feed it to the backend"""
        if self._assembly_start is None:
            self._assembly_start = frame.first_fragment_timestamp

        try:
            output = self._backend.push(frame)
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._assembly_start = None
            self._backend.reset()
            self._deliver_error(ProtocolReadError(f"Cannot decode {frame.data!r} : {e}"))
            return

        self._emit_output(output)

    def on_fragment_timeout(self) -> None:
        """The adapter received nothing within its own timeout"""
        adapter_timeout = self._adapter_engine.timeout
        self._fail_pending(
            AdapterTimeoutError(
                float("nan") if adapter_timeout is None else adapter_timeout
            )
        )

    # ┌──────────┐
    # │ Commands │
    # └──────────┘

    @staticmethod
    def _claim(command: Command[Any]) -> bool:
        """Take a command for completion, False if its caller cancelled it"""
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

    def _execute(self, command: Command[Any]) -> None:
        match command:
            case ProtocolWriteCommand():
                self._write(command)
            case ConfigureBackendCommand():
                command.action(self._backend)
                stop_conditions = self._backend.stop_conditions
                if stop_conditions is not None:
                    self._adapter_engine.set_stop_conditions(stop_conditions)
                command.set_result(None)
            case ProtocolWriteRawCommand():
                self._last_write_timestamp = time.time()
                self._chain(command, [self._adapter_engine.write(command.data)])
            case ProtocolReadCommand():
                self._begin_read(command)
            case SetProtocolTimeoutCommand():
                self._timeout = command.timeout
                command.set_result(None)
            case _ClearProtocolBufferCommand():
                self.frame_buffer.clear()
                self._backend.reset()
                self._assembly_start = None
                command.set_result(None)
            case ProtocolStopCommand():
                self._reactor.detach(self)
                command.set_result(None)
            case _:
                command.set_exception(WorkerThreadError(f"Unknown command {command!r}"))

    def _write(self, command: ProtocolWriteCommand[ProtocolT]) -> None:
        try:
            frames = self._backend.encode(command.payload)
        except (ValueError, TypeError) as e:  # UnicodeError included
            command.set_exception(
                ProtocolWriteError(f"Cannot encode {command.payload!r} : {e}")
            )
            return

        self._last_write_timestamp = time.time()
        self._chain(command, [self._adapter_engine.write(data) for data in frames])

    def _begin_read(self, command: ProtocolReadCommand[ProtocolT]) -> None:
        now = time.time()

        if command.cancelled():
            return

        if self._pending_read is not None:
            self._fail(command, WorkerThreadError("Concurrent read is not supported"))
            return

        index = self._buffered_index(command.scope)
        if index is not None:
            result = self.frame_buffer[index]
            del self.frame_buffer[index]
            if isinstance(result, BaseException):
                self._fail(command, result)
            elif self._claim(command):
                command.set_result(result)
            return

        timeout = self._timeout if command.timeout is ... else command.timeout
        self._pending_read = PendingProtocolRead(
            command=command,
            start_time=now,
            scope=command.scope,
            response_deadline=None if timeout is None else now + timeout,
            timeout=timeout,
        )

        # The adapter's own timeout covers the first fragment. It has no pending read of
        # its own here, so it has to be armed
        adapter_timeout = self._adapter_engine.timeout
        if adapter_timeout is not None and not self._backend.in_progress:
            self._adapter_engine.arm_fragment_deadline(now + adapter_timeout)

        command.add_done_callback(self._wakeup_if_cancelled)

    # ┌───────────┐
    # │ Internals │
    # └───────────┘

    def _emit_output(self, output: BackendOutput[AdapterT, ProtocolT]) -> None:
        """Send what the backend asked for, then deliver what it completed"""
        for data in output.writes:
            self._adapter_engine.write(data)

        for payload in output.payloads:
            self._deliver(payload)

    def _deliver_error(self, error: BaseException) -> None:
        """
        Hand a failure to the pending read, or keep it in order for the next one

        A frame that arrives before anyone asks for it goes to the buffer, and so must
        the failure to decode it : the read that would have received that frame is the
        one that has to see the error
        """
        pending = self._pending_read
        if pending is not None and not pending.command.cancelled():
            self._pending_read = None
            self._adapter_engine.arm_fragment_deadline(None)
            self._fail(pending.command, error)
            return
        self.frame_buffer.append(error)

    def _deliver(self, payload: ProtocolT) -> None:
        if self._last_write_timestamp is None or self._assembly_start is None:
            response_delay = float("nan")
        else:
            response_delay = self._assembly_start - self._last_write_timestamp
        self._assembly_start = None

        frame = ProtocolFrame(
            data=payload, id=self._next_frame_id(), response_delay=response_delay
        )

        pending = self._pending_read
        if pending is not None and pending.command.cancelled():
            self._pending_read = None
            pending = None

        if pending is not None and self._claim(pending.command):
            self._pending_read = None
            self._adapter_engine.arm_fragment_deadline(None)
            pending.command.set_result(frame)
        else:
            self.frame_buffer.append(frame)

    def _buffered_index(self, scope: ReadScope) -> int | None:
        """Index of the first buffered payload this read can take"""
        if scope == ReadScope.NEXT:
            return None
        for index in range(len(self.frame_buffer)):
            if scope == ReadScope.LAST_WRITE and self._last_write_timestamp is None:
                return None
            return index
        return None

    def _fail_pending(self, error: BaseException) -> None:
        pending = self._pending_read
        if pending is None:
            self._logger.debug(f"No read waiting for {error}")
            return
        self._pending_read = None
        self._adapter_engine.arm_fragment_deadline(None)
        self._fail(pending.command, error)

    def _chain(self, command: Command[None], sources: list[Command[None]]) -> None:
        """Complete command once every source has, with the first error if there is one"""
        if not sources:
            command.set_result(None)
            return

        remaining = [len(sources)]

        def on_done(source: Future[None]) -> None:
            error = None if source.cancelled() else source.exception()
            if error is not None:
                self._fail(command, error)
                return
            remaining[0] -= 1
            if remaining[0] == 0 and self._claim(command):
                command.set_result(None)

        for source in sources:
            source.add_done_callback(on_done)

    def _drop_cancelled_read(self) -> None:
        pending = self._pending_read
        if pending is not None and pending.command.cancelled():
            self._pending_read = None
            self._adapter_engine.arm_fragment_deadline(None)

    def _wakeup_if_cancelled(self, command: Future[Any]) -> None:
        if command.cancelled():
            self._reactor.wakeup()

    def _next_frame_id(self) -> int:
        output = self._frame_id
        self._frame_id += 1
        return output


class _ClearProtocolBufferCommand(Command[None]):
    """Drop the buffered payloads and the one being assembled"""


CommandT = TypeVar("CommandT", bound=Command[Any])
BackendT = TypeVar("BackendT", bound=ProtocolBackend[Any, Any])


def _stop_engine(engine: ProtocolEngine[Any, Any]) -> None:
    """Detach a protocol engine from the reactor once its protocol is collected"""
    engine.stop()


def _resolve_timeout(
    timeout: TimeoutParameterType,
    adapter: Adapter[Any, Any] | AsyncAdapter[Any, Any],
    backend: ProtocolBackend[Any, Any],
) -> TimeoutParameterType:
    """
    Time to wait for a complete protocol frame

    ``...`` keeps the timeout the user gave the adapter, and falls back on the backend
    default when they gave it none : an explicit adapter timeout is an instruction about
    the exchange, not only about its first fragment
    """
    if timeout is not ...:
        return timeout
    if adapter.has_default_timeout:
        return backend.default_timeout
    return adapter.timeout


# ┌─────────┐
# │ Facades │
# └─────────┘


class ProtocolCommon(Generic[BackendT, AdapterT, ProtocolT]):
    """
    What Protocol and AsyncProtocol share : the engine, and the read-only view on it
    """

    def __init__(
        self,
        adapter: Adapter[Any, AdapterT] | AsyncAdapter[Any, AdapterT],
        backend: BackendT,
        timeout: TimeoutParameterType,
        alias: str,
    ) -> None:
        super().__init__()
        # Public : the user built it, and the UI uses it
        self.adapter = adapter
        # Private : a user looking for the adapter must find self.adapter
        self._backend = backend
        self._engine: ProtocolEngine[AdapterT, ProtocolT] = ProtocolEngine(
            adapter.engine,
            backend,
            timeout=_resolve_timeout(timeout, adapter, backend),
            alias=alias,
        )

        adapter_timeout = backend.adapter_default_timeout
        if adapter_timeout is not ... and adapter.has_default_timeout:
            adapter.engine.set_timeout(adapter_timeout)

        weakref.finalize(self, _stop_engine, self._engine)

    @property
    def is_open(self) -> bool:
        """True if communication with the target is open"""
        return self._engine.is_open

    @property
    def timeout(self) -> TimeoutType:
        """Time to wait for a complete protocol frame"""
        return self._engine.timeout

    @property
    def engine(self) -> ProtocolEngine[AdapterT, ProtocolT]:
        """Engine of the protocol, the non-blocking side"""
        return self._engine

    def __str__(self) -> str:
        return f"{type(self).__name__}({self.adapter})"

    def __repr__(self) -> str:
        return self.__str__()


class Protocol(Generic[BackendT, AdapterT, ProtocolT],
               ProtocolCommon[BackendT, AdapterT, ProtocolT]):
    """
    Sync protocol

    Parameters
    ----------
    adapter : Adapter
    backend : ProtocolBackend
    timeout : float, None or ...
        Time to wait for a complete protocol frame, ``...`` for the backend default
    alias : str
    """

    def __init__(
        self,
        adapter: Adapter[Any, AdapterT],
        backend: BackendT,
        timeout: TimeoutParameterType = ...,
        alias: str = "",
    ) -> None:
        self._lock = threading.Lock()
        super().__init__(adapter, backend, timeout, alias)

        # Waited for, so that the adapter attributes (framing, ...) are up to date as
        # soon as the constructor returns. AsyncProtocol deliberately doesn't wait
        for future in self._engine.configuration:
            future.result()

    def open(self) -> None:
        """Open communication with the target"""
        self._engine.open().result()

    def close(self) -> None:
        """Close communication with the target"""
        self._engine.close().result()

    def set_timeout(self, timeout: TimeoutType) -> None:
        """Set the time to wait for a complete protocol frame"""
        self._engine.set_timeout(timeout).result()

    def write(self, payload: ProtocolT) -> None:
        """Encode a payload and write it to the target"""
        with self._lock:
            self._engine.write(payload).result()

    def write_raw(self, data: AdapterT) -> None:
        """Write data to the target without encoding it"""
        with self._lock:
            self._engine.write_raw(data).result()

    def read_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        scope: ReadScope | str = ReadScope.BUFFERED,
    ) -> ProtocolFrame[ProtocolT]:
        """Read one protocol frame"""
        with self._lock:
            return self._engine.read(timeout, ReadScope(scope)).result()

    def read(
        self,
        timeout: TimeoutParameterType = ...,
        scope: ReadScope | str = ReadScope.BUFFERED,
    ) -> ProtocolT:
        """Read one protocol frame and return its payload"""
        return self.read_detailed(timeout, scope).data

    def query_detailed(
        self, payload: ProtocolT, timeout: TimeoutParameterType = ...
    ) -> ProtocolFrame[ProtocolT]:
        """Write a payload and read the frame received after it"""
        with self._lock:
            self._engine.write(payload).result()
            return self._engine.read(timeout, ReadScope.LAST_WRITE).result()

    def query(self, payload: ProtocolT, timeout: TimeoutParameterType = ...) -> ProtocolT:
        """Write a payload and return the payload received after it"""
        return self.query_detailed(payload, timeout).data

    def clear_buffer(self) -> None:
        """Drop the buffered payloads, the one being assembled, and the adapter ones"""
        with self._lock:
            self._engine.clear_buffer().result()

    def register_event_callback(self, callback: Callable[[AdapterEvent], None]) -> None:
        """Register an event callback. It runs on the reactor thread and must not block"""
        self._engine.register_event_callback(callback).result()

    def clear_event_callbacks(self) -> None:
        """Remove every event callback"""
        self._engine.clear_event_callbacks().result()

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


class AsyncProtocol(Generic[BackendT, AdapterT, ProtocolT],
                    ProtocolCommon[BackendT, AdapterT, ProtocolT]):
    """
    Async protocol, same parameters as Protocol
    """

    def __init__(
        self,
        adapter: AsyncAdapter[Any, AdapterT],
        backend: BackendT,
        timeout: TimeoutParameterType = ...,
        alias: str = "",
    ) -> None:
        self._lock = asyncio.Lock()
        super().__init__(adapter, backend, timeout, alias)

    async def open(self) -> None:
        """Open communication with the target"""
        await asyncio.wrap_future(self._engine.open())

    async def close(self) -> None:
        """Close communication with the target"""
        await asyncio.wrap_future(self._engine.close())

    async def set_timeout(self, timeout: TimeoutType) -> None:
        """Set the time to wait for a complete protocol frame"""
        await asyncio.wrap_future(self._engine.set_timeout(timeout))

    async def write(self, payload: ProtocolT) -> None:
        """Encode a payload and write it to the target"""
        async with self._lock:
            await asyncio.wrap_future(self._engine.write(payload))

    async def write_raw(self, data: AdapterT) -> None:
        """Write data to the target without encoding it"""
        async with self._lock:
            await asyncio.wrap_future(self._engine.write_raw(data))

    async def read_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        scope: ReadScope | str = ReadScope.BUFFERED,
    ) -> ProtocolFrame[ProtocolT]:
        """Read one protocol frame"""
        async with self._lock:
            return await asyncio.wrap_future(self._engine.read(timeout, ReadScope(scope)))

    async def read(
        self,
        timeout: TimeoutParameterType = ...,
        scope: ReadScope | str = ReadScope.BUFFERED,
    ) -> ProtocolT:
        """Read one protocol frame and return its payload"""
        return (await self.read_detailed(timeout, scope)).data

    async def query_detailed(
        self, payload: ProtocolT, timeout: TimeoutParameterType = ...
    ) -> ProtocolFrame[ProtocolT]:
        """Write a payload and read the frame received after it"""
        async with self._lock:
            await asyncio.wrap_future(self._engine.write(payload))
            return await asyncio.wrap_future(
                self._engine.read(timeout, ReadScope.LAST_WRITE)
            )

    async def query(
        self, payload: ProtocolT, timeout: TimeoutParameterType = ...
    ) -> ProtocolT:
        """Write a payload and return the payload received after it"""
        return (await self.query_detailed(payload, timeout)).data

    async def clear_buffer(self) -> None:
        """Drop the buffered payloads, the one being assembled, and the adapter ones"""
        async with self._lock:
            await asyncio.wrap_future(self._engine.clear_buffer())

    async def register_event_callback(
        self, callback: Callable[[AdapterEvent], None]
    ) -> None:
        """Register an event callback. It runs on the reactor thread and must not block"""
        await asyncio.wrap_future(self._engine.register_event_callback(callback))

    async def clear_event_callbacks(self) -> None:
        """Remove every event callback"""
        await asyncio.wrap_future(self._engine.clear_event_callbacks())

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
