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

import asyncio
import threading
import weakref
from abc import abstractmethod
from collections.abc import Callable
from enum import Enum
from types import EllipsisType
from typing import Any, Generic, TypeVar, get_args, get_origin

from syndesi.adapters.stop_conditions import StopCondition
from syndesi.tools.errors import AdapterError

from ..component import Component, Descriptor, ReadFrame, ReadScope, WriteFrame
from ..tools.log_settings import LoggerAlias
from .adapterworker import (
    AdapterEvent,
    AdapterWorker,
    AdapterWorkerInterface,
    AddEventCallbackCommand,
    ClearEventCallbacksCommand,
    CloseCommand,
    FlushReadCommand,
    IsOpenCommand,
    OpenCommand,
    ReadCommand,
    SetTimeoutCommand,
    StopThreadCommand,
    WriteCommand,
)
from .utils import TimeoutParameterType, TimeoutType

DataT = TypeVar("DataT")

# pylint: disable=too-many-public-methods, too-many-instance-attributes
class Adapter(Generic[DataT], AdapterWorkerInterface[DataT], Component[DataT]):
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
        worker: AdapterWorker[DataT],
        timeout: TimeoutParameterType,
        # stop_conditions : StopCondition | list[StopCondition] | EllipsisType,
        alias: str,
        # encoding: str = "utf-8",
        auto_open: bool = True,
    ) -> None:
        Component.__init__(self, LoggerAlias.ADAPTER)
        AdapterWorkerInterface.__init__(self)

        self._alias = alias
        self._worker = worker
        self._auto_open = auto_open
        self._timeout : TimeoutType

        # Default timeout
        self.is_default_timeout = timeout is Ellipsis

        self._initial_timeout : float | None
        if timeout is ...:
            self._initial_timeout = self.default_timeout()
        elif timeout is None:
            self._initial_timeout = None
        else:
            try:
                self._initial_timeout = float(timeout)
            except (ValueError, TypeError) as e:
                raise ValueError(f"Invalid timeout : {timeout}") from e

        # Serialize read/write/query ordering for sync callers.
        self._sync_io_lock = threading.Lock()
        # Serialize read/write/query ordering for async callers.
        self._async_io_lock = asyncio.Lock()

        self._logger.info(f"Setting up {self.descriptor} adapter ")
        self.set_timeout(self._initial_timeout)

        if self.descriptor.is_initialized() and self._auto_open:
            self.open()

        weakref.finalize(self, self._cleanup)

    @property
    @abstractmethod
    def descriptor(self) -> Descriptor:
        ...

    # ┌──────────────────────────┐
    # │ Defaults / configuration │
    # └──────────────────────────┘

    def _stop(self) -> None:
        cmd = StopThreadCommand()
        self._worker.send_command(cmd)
        try:
            cmd.result(self.WorkerTimeout.STOP.value)
        except AdapterError:
            pass

    @staticmethod
    @abstractmethod
    def default_timeout() -> float | None:
        """Default timeout"""
        raise NotImplementedError

    def __str__(self) -> str:
        return str(self.descriptor)

    def __repr__(self) -> str:
        return self.__str__()

    def _cleanup(self) -> None:
        try:
            if self.is_open():
                self.close()
        except AdapterError:
            pass
        self._stop()

    # ┌────────────┐
    # │ Public API │
    # └────────────┘

    def set_timeout(self, timeout: TimeoutType) -> None:
        """
        Set adapter timeout

        Parameters
        ----------
        timeout : float | int | None
        """
        # This is read by the worker when ReadCommand.timeout is ...
        cmd = SetTimeoutCommand(timeout)
        self._worker.send_command(cmd)
        cmd.result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)
        self._timeout = timeout

    @property
    def timeout(self) -> TimeoutType:
        return self._timeout

    def set_default_timeout(self, default_timeout: TimeoutType) -> None:
        """
        Configure adapter default timeout. Timeout will only be set if none
        has been configured before

        Parameters
        ----------
        default_timeout : float | int | None
        """
        if self.is_default_timeout:
            self._logger.debug(f"Setting default timeout to {default_timeout}")
            self.set_timeout(default_timeout)

    def register_event_callback(self, event_callback: Callable[[AdapterEvent], None]) -> None:
        """
        Configure event callback. Event callback is called as such :

        callback(event : AdapterEvent)

        Parameters
        ----------
        event_callback : Callable[[AdapterEvent], None]

        """
        cmd = AddEventCallbackCommand(event_callback)
        self._worker.send_command(cmd)
        cmd.result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)

    def clear_event_callbacks(self) -> None:
        cmd = ClearEventCallbacksCommand()
        self._worker.send_command(cmd)
        cmd.result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)

    @property
    def frame_buffer(self) -> list[ReadFrame[Any]]:
        """Return a list of ReadFrame available in the frame buffer"""
        return list(self._worker.frame_buffer)

    # ==== open ====

    def _open_future(self) -> OpenCommand:
        cmd = OpenCommand()
        self._worker.send_command(cmd)
        return cmd

    def open(self) -> None:
        """
        Open adapter communication with the target (blocking)
        """
        
        # If timeout is None, wait indefinitely
        # If timeout is not None, add a small amount (IMMEDIATE_COMMAND)
        # To let the worker setup and respond. The "real" timeout is used in the _worker_open
        # method
        timeout : float | None
        if self.timeout is None:
            timeout = None
        else:
            timeout = self.timeout + self.WorkerTimeout.IMMEDIATE_COMMAND.value

        output = self._open_future().result(timeout)
        return output

    async def aopen(self) -> None:
        """
        Open adapter communication with the target (async)
        """
        await asyncio.wrap_future(self._open_future())

    # ==== close ====

    def _close_future(self) -> CloseCommand:
        cmd = CloseCommand()
        self._worker.send_command(cmd)
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
        timeout: TimeoutParameterType,
        scope: ReadScope,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition],
    ) -> ReadCommand[DataT]:
        cmd: ReadCommand[DataT] = ReadCommand(
            timeout=timeout, scope=scope, stop_conditions=stop_conditions
        )
        self._worker.send_command(cmd)
        return cmd

    def read_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ReadFrame[DataT]:
        with self._sync_io_lock:
            result = self._read_detailed_future(
                timeout=timeout, scope=ReadScope(scope), stop_conditions=stop_conditions
            ).result(self.WorkerTimeout.READ.value)
        return result

    async def aread_detailed(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ReadFrame[DataT]:
        async with self._async_io_lock:
            return await asyncio.wrap_future(
                self._read_detailed_future(
                    timeout=timeout, scope=ReadScope(scope), stop_conditions=stop_conditions
                )
            )

    # ==== read ====

    def read(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> DataT:
        frame = self.read_detailed(
            timeout=timeout, scope=scope, stop_conditions=stop_conditions
        )
        return frame.data

    async def aread(
        self,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.BUFFERED,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> DataT:
        frame = await self.aread_detailed(
            timeout=timeout, scope=scope, stop_conditions=stop_conditions
        )
        return frame.data

    # ==== flush_read ====

    def _flush_read_future(self) -> FlushReadCommand:
        cmd = FlushReadCommand()
        self._worker.send_command(cmd)
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

    def _write_future(self, data: DataT) -> WriteCommand[DataT]:
        cmd = WriteCommand(WriteFrame(data))
        self._worker.send_command(cmd)
        return cmd

    def write(self, data: DataT) -> None:
        with self._sync_io_lock:
            self._write_future(data).result(self.WorkerTimeout.WRITE.value)

    async def awrite(self, data: DataT) -> None:
        async with self._async_io_lock:
            await asyncio.wrap_future(self._write_future(data))

    # ==== query ====

    async def aquery_detailed(
        self,
        payload: DataT,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.LAST_WRITE.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ReadFrame[DataT]:
        async with self._async_io_lock:
            await asyncio.wrap_future(self._flush_read_future())
            await asyncio.wrap_future(self._write_future(payload))
            return await asyncio.wrap_future(
                self._read_detailed_future(
                    timeout=timeout, scope=ReadScope(scope), stop_conditions=stop_conditions
                )
            )

    def query_detailed(
        self,
        payload: DataT,
        timeout: TimeoutParameterType = ...,
        scope: str = ReadScope.LAST_WRITE.value,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> ReadFrame[DataT]:

        with self._sync_io_lock:
            self._flush_read_future().result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)
            self._write_future(payload).result(self.WorkerTimeout.WRITE.value)
            output = self._read_detailed_future(
                timeout=timeout, scope=ReadScope(scope), stop_conditions=stop_conditions
            ).result(self.WorkerTimeout.READ.value)
        return output

    # ==== Other ====

    def _is_open_future(self) -> IsOpenCommand:
        cmd = IsOpenCommand()
        self._worker.send_command(cmd)
        return cmd

    def is_open(self) -> bool:
        """Check if the adapter is open"""
        return self._is_open_future().result(self.WorkerTimeout.IMMEDIATE_COMMAND.value)

    async def ais_open(self) -> bool:
        """Asynchronously check if the adapter is open"""
        return await asyncio.wrap_future(self._is_open_future())

# def find_adapter_data_type(cls: type) -> object:
#     for base in get_original_bases(cls):
#         origin = get_origin(base)
#         if origin is AdapterBase:
#             args = get_args(base)
#             if args:
#                 return args[0]
#         else:
#             raise TypeError("Class is not an Adapter")
#     return None

def find_adapter_data_type(obj : type[Adapter[Any]] | Adapter[Any]) -> Any:
    """
    Supports:
    - Adapter[bytes]
    - class MyAdapter(Adapter[bytes]): ...
    - MyAdapter() instance

    Returns the concrete DataT, or None if it cannot be determined.
    """

    # Case 1: direct parametrized generic, e.g. Adapter[bytes]
    if get_origin(obj) is Adapter:
        args = get_args(obj)
        return args[0] if args else None

    # Normalize class / instance
    cls = obj if isinstance(obj, type) else type(obj)

    # Case 2: subclass, e.g. class MyAdapter(Adapter[bytes])
    bases = getattr(cls, "__orig_bases__", cls.__bases__)
    for base in bases:
        if get_origin(base) is Adapter:
            args = get_args(base)
            return args[0] if args else None

    return None
