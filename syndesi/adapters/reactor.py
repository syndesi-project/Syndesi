# File : reactor.py
# Author : Sébastien Deriaz
# License : GPL
"""
Reactor, the single background thread of Syndesi

One select() call watches every attached engine, so a process running twenty
instruments still runs one thread. The reactor holds no per-adapter state, it only
dispatches to the ReactorClient interface below
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from collections.abc import Callable
from select import select
from typing import Protocol, runtime_checkable

from ..tools.log_settings import LoggerAlias
from .utils import HasFileno, nmin

_WAKEUP_BYTE = b"\x00"


@runtime_checkable
class ReactorClient(Protocol):
    """
    What the reactor needs from an engine. Every method runs on the reactor thread
    """

    def selectable(self) -> HasFileno | None:
        """Object to watch for incoming data, None if there is nothing to watch"""

    def next_deadline(self) -> float | None:
        """Earliest timestamp at which on_deadline must be called"""

    def drain_commands(self) -> None:
        """Run every queued command"""

    def on_readable(self, now: float) -> None:
        """Data is available on the selectable"""

    def on_deadline(self, now: float) -> None:
        """A deadline returned by next_deadline has been reached"""


class Reactor:
    """
    Background thread running a select loop over every attached client
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger(LoggerAlias.REACTOR.value)
        self._clients: list[ReactorClient] = []
        self._lock = threading.Lock()
        self._running = True

        self._wakeup_r, self._wakeup_w = socket.socketpair()
        self._wakeup_r.setblocking(False)
        self._wakeup_w.setblocking(False)

        self._thread = threading.Thread(
            target=self._run, daemon=True, name="syndesi-reactor"
        )
        self._thread.start()

    def attach(self, client: ReactorClient) -> None:
        """
        Add a client to the loop
        """
        with self._lock:
            if client not in self._clients:
                self._clients.append(client)
        self.wakeup()

    def detach(self, client: ReactorClient) -> None:
        """
        Remove a client from the loop
        """
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)
        self.wakeup()

    def wakeup(self) -> None:
        """
        Interrupt the select call, called whenever a command is queued
        """
        try:
            self._wakeup_w.send(_WAKEUP_BYTE)
        except OSError:
            pass

    def stop(self) -> None:
        """
        Stop the loop. The reactor cannot be restarted
        """
        self._running = False
        self.wakeup()
        self._thread.join(timeout=1.0)
        self._wakeup_r.close()
        self._wakeup_w.close()

    # ┌───────────┐
    # │ Main loop │
    # └───────────┘

    def _run(self) -> None:
        while self._running:
            try:
                self._iterate()
            except Exception as e:  # pylint: disable=broad-exception-caught
                # The loop is shared, one misbehaving client must not stop the others
                self._logger.exception(f"Reactor iteration failed : {e}")

    def _iterate(self) -> None:
        clients = self._snapshot()
        watched, deadline = self._watched(clients)
        timeout = None if deadline is None else max(0.0, deadline - time.time())

        readable, _, _ = select([self._wakeup_r, *watched], [], [], timeout)
        now = time.time()

        if self._wakeup_r in readable:
            # Draining before taking the list is what makes the wakeup reliable : a
            # client always appends itself (or queues its command) before sending its
            # byte, so a byte consumed here belongs to a client the next snapshot sees
            self._drain_wakeup()
            for client in self._snapshot():
                self._safe(client.drain_commands)
            # Opening or closing changes the selectables, rebuild them before waiting
            return

        if readable:
            for selectable in readable:
                self._safe(watched[selectable].on_readable, now)
            return

        for client in clients:
            self._safe(client.on_deadline, now)

    def _snapshot(self) -> list[ReactorClient]:
        with self._lock:
            return list(self._clients)

    def _watched(
        self, clients: list[ReactorClient]
    ) -> tuple[dict[HasFileno, ReactorClient], float | None]:
        """
        Return the selectables to watch and the earliest deadline among the clients
        """
        watched: dict[HasFileno, ReactorClient] = {}
        deadline: float | None = None

        for client in clients:
            selectable = client.selectable()
            if selectable is not None and _usable(selectable):
                watched[selectable] = client
            deadline = nmin(deadline, client.next_deadline())

        return watched, deadline

    def _drain_wakeup(self) -> None:
        while True:
            try:
                if not self._wakeup_r.recv(1024):
                    return
            except (BlockingIOError, OSError):
                return

    def _safe(self, method: Callable[..., None], *args: float) -> None:
        try:
            method(*args)
        except Exception as e:  # pylint: disable=broad-exception-caught
            self._logger.exception(f"Reactor client failed : {e}")


def _usable(selectable: HasFileno) -> bool:
    """
    Return True if the selectable can be passed to select

    A backend that just closed still shows up for one iteration, and a single bad
    file descriptor would make select fail for every other adapter
    """
    try:
        return selectable.fileno() >= 0
    except (OSError, ValueError):
        return False


class _Default:
    """Holder for the shared reactor, created on first use"""

    instance: Reactor | None = None
    lock = threading.Lock()


def default_reactor() -> Reactor:
    """
    Return the reactor shared by every adapter that doesn't ask for its own
    """
    with _Default.lock:
        if _Default.instance is None:
            _Default.instance = Reactor()
        return _Default.instance
