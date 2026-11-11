# File : worker.py
# Author : Sébastien Deriaz
# License : GPL
"""
The thread every call to a component runs on

Building the stack, opening, reading (which waits for the timeout), the commands of a
driver : all of them can block, none of them may run on the GUI thread. They run one at
a time, in the order they were asked, on a single thread that also owns an asyncio loop
for the async components (AsyncIP, AsyncSCPI, ...) : a call returning an awaitable is
run to completion there

Events emitted by the reactor thread are forwarded with a Qt signal, which Qt delivers
on the GUI thread
"""

from __future__ import annotations

import asyncio
import inspect
import queue
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal

Callback = Callable[[Any, BaseException | None], None]


@dataclass
class _Job:
    function: Callable[[], Any]
    on_done: Callback | None
    # Counted in the pending calls (submit), call_sync isn't
    counted: bool = True


class Worker(QObject):
    """Runs the calls to the components on a dedicated thread"""

    busy_changed = Signal(bool)
    _done = Signal(object, object, object)

    def __init__(self) -> None:
        super().__init__()
        self._jobs: queue.SimpleQueue[_Job | None] = queue.SimpleQueue()
        self._pending = 0
        self._done.connect(self._dispatch, Qt.ConnectionType.QueuedConnection)
        # Created by the thread, which owns it
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread = threading.Thread(target=self._run, name="syndesi-ui", daemon=True)
        self._thread.start()

    @property
    def busy(self) -> bool:
        """True while calls are waiting or running"""
        return self._pending > 0

    def submit(self, function: Callable[[], Any], on_done: Callback | None = None) -> None:
        """
        Run function on the worker thread, then on_done(result, error) on the GUI thread
        """
        self._pending += 1
        if self._pending == 1:
            self.busy_changed.emit(True)
        self._jobs.put(_Job(function, on_done))

    def call_sync(self, function: Callable[[], Any], timeout: float = 5.0) -> Any:
        """Run function on the worker thread and wait for it (shutdown only)"""
        event = threading.Event()
        box: list[Any] = [None, None]

        def job() -> None:
            try:
                assert self._loop is not None
                box[0] = _run_to_completion(self._loop, function)
            except BaseException as e:  # pylint: disable=broad-exception-caught
                box[1] = e
            event.set()

        self._jobs.put(_Job(job, None, counted=False))
        event.wait(timeout)
        result, error = box
        if error is not None:
            raise error
        return result

    def stop(self) -> None:
        """Stop the thread once the calls asked for are done"""
        self._jobs.put(None)
        self._thread.join(timeout=2)

    def _run(self) -> None:
        loop = self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while True:
            job = self._jobs.get()
            if job is None:
                break
            result: Any = None
            error: BaseException | None = None
            try:
                result = _run_to_completion(loop, job.function)
            except BaseException as e:  # pylint: disable=broad-exception-caught
                error = e
                error.__syndesi_traceback__ = traceback.format_exc()  # type: ignore[attr-defined]
            if job.counted:
                self._done.emit(job.on_done, result, error)
        loop.close()

    def _dispatch(self, on_done: Callback | None, result: Any, error: BaseException | None) -> None:
        self._pending = max(0, self._pending - 1)
        if self._pending == 0:
            self.busy_changed.emit(False)
        if on_done is not None:
            on_done(result, error)


def _run_to_completion(loop: asyncio.AbstractEventLoop, function: Callable[[], Any]) -> Any:
    result = function()
    if inspect.isawaitable(result):
        result = loop.run_until_complete(_await(result))
    return result


async def _await(awaitable: Any) -> Any:
    return await awaitable


def error_text(error: BaseException) -> str:
    """One line describing an error"""
    text = str(error)
    name = type(error).__name__
    return f"{name} : {text}" if text else name


def resolve(value: Any) -> Any:
    """
    Inside a job : wait for value if it is awaitable (the call was made on an async
    component), return it unchanged otherwise
    """
    if inspect.isawaitable(value):
        loop = asyncio.get_event_loop_policy().get_event_loop()
        return loop.run_until_complete(_await(value))
    return value
