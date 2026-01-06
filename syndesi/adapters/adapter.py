# File : adapter.py
# Author : Sébastien Deriaz
# License : GPL

"""
Adapters provide a common abstraction for the media layers (physical + data link + network)

The user calls methods of the Adapter class synchronously.

An adapter is meant to work with bytes objects but it can accept strings.
Strings will automatically be converted to bytes using utf-8 encoding

Each adapter contains a worker thread that monitors the low-level communication layers.
This approach allows for precise time management (when each fragment is sent/received) and allows
for asynchronous events (fragment received).

Async facade:
- aopen/awrite/aread/aread_detailed simply await the SAME underlying worker-thread commands
  using asyncio.wrap_future (no extra threads are spawned).
"""

# NOTE:
# This version removes the "worker publishes events into a queue that read_detailed consumes".
# Instead:
# - The worker continuously assembles AdapterFrame from fragments (as before).
# - A read_detailed command registers a "pending read" inside the worker.
# - When a frame completes, the worker either:
#     * completes the pending read future, OR
#     * buffers the frame for later buffered reads, and optionally calls the callback.
#
# This avoids having a sync queue AND an async queue, and makes async wrappers trivial.

import asyncio
import threading
import weakref
from abc import abstractmethod
from collections.abc import Callable
from enum import Enum
from types import EllipsisType

from syndesi.tools.errors import AdapterError

from ..component import AdapterFrame, Component, Descriptor, ReadScope
from ..tools.log_settings import LoggerAlias
from ..tools.types import NumberLike, is_number
from .adapter_worker import (
    AdapterEvent,
    AdapterWorker,
    CloseCommand,
    FlushReadCommand,
    IsOpenCommand,
    OpenCommand,
    ReadCommand,
    SetDescriptorCommand,
    SetEventCallbackCommand,
    SetStopConditionsCommand,
    SetTimeoutCommand,
    StopThreadCommand,
    WriteCommand,
)
from .stop_conditions import Fragment, StopCondition
from .timeout import Timeout, TimeoutAction, any_to_timeout

fragments: list[Fragment]


# pylint: disable=too-many-public-methods, too-many-instance-attributes
class Adapter(Component[bytes], AdapterWorker):
    """
    Adapter class

    An adapter manages communication with a hardware device.
    """

    class WorkerTimeout(Enum):
        """Timeout value for each worker command scenario"""

        OPEN = 2
        STOP = 1
        IMMEDIATE_COMMAND = 0.2
        CLOSE = 0.5
        WRITE = 0.5
        READ = None

    def __init__(
        self,
        *,
        descriptor: Descriptor,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition],
        timeout: Timeout | EllipsisType | NumberLike | None,
        alias: str,
        encoding: str = "utf-8",
        event_callback: Callable[[AdapterEvent], None] | None = None,
        auto_open: bool = True,
    ) -> None:
        super().__init__(LoggerAlias.ADAPTER)
        self.encoding = encoding
        self._alias = alias

        self.descriptor = descriptor
        self.auto_open = auto_open

        self._initial_event_callback = event_callback

        # Default stop conditions
        self._initial_stop_conditions: list[StopCondition]
        if stop_conditions is ...:
            self._is_default_stop_condition = True
            self._initial_stop_conditions = self._default_stop_conditions()
        else:
            self._is_default_stop_condition = False
            if isinstance(stop_conditions, StopCondition):
                self._initial_stop_conditions = [stop_conditions]
            elif isinstance(stop_conditions, list):
                self._initial_stop_conditions = stop_conditions
            else:
                raise ValueError("Invalid stop_conditions")

        # Default timeout
        self.is_default_timeout = timeout is Ellipsis

        if timeout is Ellipsis:
            self._initial_timeout = self._default_timeout()
        elif isinstance(timeout, Timeout):
            self._initial_timeout = timeout
        elif is_number(timeout):
            self._initial_timeout = Timeout(timeout, action=TimeoutAction.ERROR)
        elif timeout is None:
            self._initial_timeout = Timeout(None)
        else:
            raise ValueError(f"Invalid timeout : {timeout}")

        # Worker thread
        self._worker_thread = threading.Thread(
            target=self._worker_thread_method, daemon=True
        )
        self._worker_thread.start()

        # Serialize read/write/query ordering for sync callers.
        self._sync_io_lock = threading.Lock()
        # Serialize read/write/query ordering for async callers.
        self._async_io_lock = asyncio.Lock()

        self._logger.info(f"Setting up {self.descriptor} adapter ")
        self._update_descriptor()
        self.set_stop_conditions(self._initial_stop_conditions)
        self.set_timeout(self._initial_timeout)
        self.set_event_callback(self._initial_event_callback)

        if self.descriptor.is_initialized() and auto_open:
            self.open()

        weakref.finalize(self, self._cleanup)

    # ┌──────────────────────────┐
    # │ Defaults / configuration │
    # └──────────────────────────┘

    def _stop(self) -> None:
        cmd = StopThreadCommand()
        self._worker_send_command(cmd)
        try:
            cmd.result(self.WorkerTimeout.STOP.value)
        except AdapterError:
            pass

    def _update_descriptor(self) -> None:
        cmd = SetDescriptorCommand(self.descriptor)
        self._worker_send_command(cmd)
        cmd.result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)

    @abstractmethod
    def _default_timeout(self) -> Timeout:
        raise NotImplementedError

    @abstractmethod
    def _default_stop_conditions(self) -> list[StopCondition]:
        raise NotImplementedError

    def __str__(self) -> str:
        return str(self.descriptor)

    def __repr__(self) -> str:
        return self.__str__()

    def _cleanup(self) -> None:
        # Be defensive: finalizers can run at interpreter shutdown.
        try:
            if self.is_open():
                self.close()
        except AdapterError:
            pass

        self._stop()

        try:
            self._command_queue_r.close()
            self._command_queue_w.close()
        except AdapterError:
            pass

    # ┌────────────┐
    # │ Public API │
    # └────────────┘

    def set_timeout(self, timeout: Timeout | None | float) -> None:
        """
        Set adapter timeout

        Parameters
        ----------
        timeout : Timeout, float or None
        """
        # This is read by the worker when ReadCommand.timeout is ...
        timeout_instance = any_to_timeout(timeout)
        cmd = SetTimeoutCommand(timeout_instance)
        self._worker_send_command(cmd)
        cmd.result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)

    def set_default_timeout(self, default_timeout: Timeout | None) -> None:
        """
        Configure adapter default timeout. Timeout will only be set if none
        has been configured before

        Parameters
        ----------
        default_timeout : Timeout or None
        """
        if self.is_default_timeout:
            new_timeout = any_to_timeout(default_timeout)
            self._logger.debug(f"Setting default timeout to {new_timeout}")
            self.set_timeout(new_timeout)

    def set_stop_conditions(
        self, stop_conditions: StopCondition | None | list[StopCondition]
    ) -> None:
        """
        Set adapter stop-conditions

        Parameters
        ----------
        stop_conditions : [StopCondition] or None
        """
        if isinstance(stop_conditions, list):
            lst = stop_conditions
        elif isinstance(stop_conditions, StopCondition):
            lst = [stop_conditions]
        elif stop_conditions is None:
            lst = []
        else:
            raise ValueError("Invalid stop_conditions")

        cmd = SetStopConditionsCommand(lst)
        self._worker_send_command(cmd)
        cmd.result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)

    def set_default_stop_conditions(self, stop_conditions: list[StopCondition]) -> None:
        """
        Configure adapter default stop-condition. Stop-condition will only be set if none
        has been configured before

        Parameters
        ----------
        stop_conditions : [StopCondition]
        """
        if self._is_default_stop_condition:
            self.set_stop_conditions(stop_conditions)

    def set_event_callback(
        self, callback: Callable[[AdapterEvent], None] | None
    ) -> None:
        """
        Configure event callback. Event callback is called as such :

        callback(event : AdapterEvent)

        Parameters
        ----------
        callback : callable

        """
        cmd = SetEventCallbackCommand(callback)
        self._worker_send_command(cmd)
        cmd.result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)

    # ==== open ====

    def _open_future(self) -> OpenCommand:
        cmd = OpenCommand()
        self._worker_send_command(cmd)
        return cmd

    def open(self) -> None:
        """
        Open adapter communication with the target (blocking)
        """
        return self._open_future().result(self.WorkerTimeout.OPEN.value)

    async def aopen(self) -> None:
        """
        Open adapter communication with the target (async)
        """
        await asyncio.wrap_future(self._open_future())

    # ==== close ====

    def _close_future(self) -> CloseCommand:
        cmd = CloseCommand()
        self._worker_send_command(cmd)
        return cmd

    def close(self) -> None:
        """
        Close adapter communication with the target (blocking)
        """
        self._close_future().result(self.WorkerTimeout.CLOSE.value)

    async def aclose(self) -> None:
        """
        Close adapter communication with the target (async)
        """
        await asyncio.wrap_future(self._close_future())

    # ==== read_detailed ====

    def _read_detailed_future(
        self,
        timeout: Timeout | EllipsisType | None,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition],
        scope: str,
    ) -> ReadCommand:
        cmd = ReadCommand(
            timeout=timeout,
            stop_conditions=stop_conditions,
            scope=ReadScope(scope),
        )
        self._worker_send_command(cmd)
        return cmd

    def read_detailed(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> AdapterFrame:
        with self._sync_io_lock:
            return self._read_detailed_future(
                timeout=timeout, stop_conditions=stop_conditions, scope=scope
            ).result(self.WorkerTimeout.READ.value)

    async def aread_detailed(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> AdapterFrame:
        async with self._async_io_lock:
            return await asyncio.wrap_future(
                self._read_detailed_future(
                    timeout=timeout, stop_conditions=stop_conditions, scope=scope
                )
            )

    # ==== read ====

    def read(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> bytes:
        frame = self.read_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )
        return frame.get_payload()

    async def aread(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> bytes:
        frame = await self.aread_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )
        return frame.get_payload()

    # ==== flush_read ====

    def _flush_read_future(self) -> FlushReadCommand:
        cmd = FlushReadCommand()
        self._worker_send_command(cmd)
        return cmd

    async def aflush_read(self) -> None:
        """
        Clear buffered completed frames and reset current fragment assembly (async)
        """
        async with self._async_io_lock:
            await asyncio.wrap_future(self._flush_read_future())

    def flush_read(self) -> None:
        """
        Clear buffered completed frames and reset current fragment assembly (blocking)
        """
        with self._sync_io_lock:
            self._flush_read_future().result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)

    # ==== write ====

    def _write_future(self, data: bytes | str) -> WriteCommand:
        if isinstance(data, str):
            data = data.encode(self.encoding)
        cmd = WriteCommand(data)
        self._worker_send_command(cmd)
        return cmd

    def write(self, data: bytes | str) -> None:
        with self._sync_io_lock:
            self._write_future(data).result(self.WorkerTimeout.WRITE.value)

    async def awrite(self, data: bytes | str) -> None:
        async with self._async_io_lock:
            await asyncio.wrap_future(self._write_future(data))

    # ==== query ====

    async def aquery_detailed(
        self,
        payload: bytes,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> AdapterFrame:
        async with self._async_io_lock:
            await self.aflush_read()
            await self.awrite(payload)
            return await self.aread_detailed(
                timeout=timeout, stop_conditions=stop_conditions, scope=scope
            )

    def query_detailed(
        self,
        payload: bytes,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> AdapterFrame:

        with self._sync_io_lock:
            self.flush_read()
            self.write(payload)
            return self.read_detailed(
                timeout=timeout, stop_conditions=stop_conditions, scope=scope
            )

    # ==== Other ====

    def _is_open_future(self) -> IsOpenCommand:
        cmd = IsOpenCommand()
        self._worker_send_command(cmd)
        return cmd

    def is_open(self) -> bool:
        """Check if the adapter is open"""
        return self._is_open_future().result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)

    async def ais_open(self) -> bool:
        """Asynchronously check if the adapter is open"""
        return await asyncio.wrap_future(self._is_open_future())
