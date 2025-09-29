# File : backend.py
# Author : Sébastien Deriaz
# License : GPL
#
# The backend is responsible for managing incoming client connections (frontend)
# and creating backend client threads if necessary


import argparse
import logging
import os
import select
import threading
import time
from collections.abc import Callable
from multiprocessing.connection import Client, Listener
from types import EllipsisType
from typing import Any, TypeGuard, cast

from syndesi.adapters.backend.adapter_backend import Selectable
from syndesi.adapters.backend.backend_tools import NamedConnection
from syndesi.tools.types import NumberLike

from ...tools.backend_api import (
    BACKEND_PORT,
    LOCALHOST,
    Action,
    BackendResponse,
    frontend_send,
)
from ...tools.log_settings import LoggerAlias
from .adapter_session import AdapterSession

# There is a single backend, each connection to the backend creates a thread
# We need something to manage all of these threads so that two can access the same ressource

DEFAULT_BACKEND_SHUTDOWN_DELAY = 2
DEFAULT_SESSION_SHUTDOWN_DELAY = 2


class LogRelayHandler(logging.Handler):
    def __init__(self, history_size: int = 100):
        super().__init__()
        self.connections: set[NamedConnection] = (
            set()
        )  # Set of active logger connections
        self.connections_lock = threading.Lock()
        self.log_history: list[logging.LogRecord] = []
        self.log_history_lock = threading.Lock()
        self.history_size = history_size

    def add_connection(
        self, conn: NamedConnection, delete_callback: Callable[[NamedConnection], None]
    ) -> None:
        # Send log history to the new connection
        with self.log_history_lock:
            for record in self.log_history:
                try:
                    conn.conn.send(record)
                except (BrokenPipeError, OSError):
                    delete_callback(conn)
                    return
        # Add to active connections
        with self.connections_lock:
            self.connections.add(conn)

    def remove_connection(self, conn: NamedConnection) -> None:
        with self.connections_lock:
            self.connections = {c for c in self.connections if c != conn}

    def emit(self, record: logging.LogRecord) -> None:
        # Add to history
        with self.log_history_lock:
            self.log_history.append(record)
            if len(self.log_history) > self.history_size:
                self.log_history.pop(0)
        # Broadcast to all connections
        to_remove: list[NamedConnection] = []
        with self.connections_lock:
            for conn in list(self.connections):
                try:
                    conn.conn.send(record)
                except (BrokenPipeError, OSError):
                    to_remove.append(conn)

        for conn in to_remove:
            self.remove_connection(conn)


def is_request(x: object) -> TypeGuard[tuple[str, object]]:
    if not isinstance(x, tuple) or not x:
        return False
    if not isinstance(x[0], str):
        return False

    return True


class Backend:
    MONITORING_DELAY = 0.5
    _session_shutdown_delay: NumberLike | None
    _backend_shutdown_delay: NumberLike | None
    _backend_shutdown_timestamp: NumberLike | None
    shutdown_timer: threading.Timer | None

    def __init__(
        self,
        host: str,
        port: int,
        backend_shutdown_delay: None | NumberLike | EllipsisType = ...,
        session_shutdown_delay: None | NumberLike | EllipsisType = ...,
    ):

        if backend_shutdown_delay is ...:
            self._backend_shutdown_delay = DEFAULT_BACKEND_SHUTDOWN_DELAY
        else:
            self._backend_shutdown_delay = backend_shutdown_delay

        if session_shutdown_delay is ...:
            self._session_shutdown_delay = DEFAULT_SESSION_SHUTDOWN_DELAY
        else:
            self._session_shutdown_delay = session_shutdown_delay

        if self._backend_shutdown_delay is None:
            self._backend_shutdown_timestamp = None
        else:
            self._backend_shutdown_timestamp = (
                time.time() + self._backend_shutdown_delay
            )

        self.host = host
        self.port = port

        # self.adapters_lock = threading.Lock()
        self.listener: Listener = Listener((self.host, self.port), backlog=10)
        self.adapter_sessions: dict[str, AdapterSession] = {}
        self.shutdown_timer = None

        # Monitoring connections
        self._monitoring_connections: list[NamedConnection] = []

        # Logger connections
        # self._logger_connections: list[NamedConnection] = []

        # Configure loggers
        self._log_handler = LogRelayHandler(history_size=100)

        self._adapter_session_logger = logging.getLogger(
            LoggerAlias.ADAPTER_BACKEND.value
        )
        self._adapter_session_logger.addHandler(self._log_handler)
        self._adapter_session_logger.setLevel(logging.DEBUG)
        self._logger = logging.getLogger(LoggerAlias.BACKEND.value)
        self._logger.setLevel(logging.DEBUG)
        self._logger.addHandler(self._log_handler)

        self._logger.info(f"Init backend on {self.host}:{self.port}")

        self.running = True

    def _remove_logger_connection(self, conn: NamedConnection) -> None:
        self._log_handler.remove_connection(conn)
        self._update_monitoring(monitoring_sessions=True)

    def _remove_monitoring_connection(self, conn: NamedConnection) -> None:
        try:
            self._monitoring_connections.remove(conn)
        except ValueError:
            pass
        self._update_monitoring(monitoring_sessions=True)

    def _remove_session(self, descriptor: str) -> None:
        self._logger.info(f"Remove adapter session {descriptor}")
        # with self.adapters_lock:
        self.adapter_sessions.pop(descriptor, None)
        self._update_monitoring(adapter_sessions=True)

    def manage_monitoring_clients(self, conn: NamedConnection) -> None:
        try:
            raw: object = conn.conn.recv()
        except (EOFError, ConnectionResetError):
            # Monitor disconnected
            # Remove from the list of monitoring connections
            self._monitoring_connections.remove(conn)
            conn.conn.close()
        else:
            response: BackendResponse
            response = (Action.ERROR_GENERIC, "Unknown error")
            if not is_request(raw):
                response = (
                    Action.ERROR_INVALID_REQUEST,
                    "Invalid backend debugger request",
                )
            else:
                action: Action = Action(raw[0])

                if action == Action.BACKEND_STATS:
                    response = (Action.BACKEND_STATS, os.getpid())
                elif action == Action.SET_LOG_LEVEL:
                    response = (Action.SET_LOG_LEVEL,)
                    level: int = cast(int, raw[1])
                    self._logger.setLevel(level)
                    self._adapter_session_logger.setLevel(level)
                else:
                    response = (Action.ERROR_UNKNOWN_ACTION, f"{action}")

            if not frontend_send(conn.conn, *response):
                self._monitoring_connections.remove(conn)

    def _broadcast_to_monitoring_clients(self, action: Action, *args: Any) -> None:
        for conn in self._monitoring_connections:
            if not frontend_send(conn.conn, action, *args):
                self._remove_monitoring_connection(conn)

    def _update_monitoring(
        self,
        adapter_sessions: bool = False,
        monitoring_sessions: bool = False,
        stats: bool = False,
    ) -> None:
        if adapter_sessions:
            snapshot: dict[str, tuple[bool, list[str]]] = {}
            for adapter_descriptor, thread in self.adapter_sessions.items():
                adapter_clients = thread.enumerate_connections()
                status = thread.is_adapter_opened()
                snapshot[adapter_descriptor] = status, adapter_clients
            self._broadcast_to_monitoring_clients(
                Action.ENUMERATE_ADAPTER_CONNECTIONS, snapshot
            )

        if monitoring_sessions:
            self._broadcast_to_monitoring_clients(
                Action.ENUMERATE_MONITORING_CONNECTIONS,
                [(x.remote(), "logging") for x in self._log_handler.connections]
                + [(x.remote(), "monitoring") for x in self._monitoring_connections],
            )

        if stats:
            self._broadcast_to_monitoring_clients(Action.BACKEND_STATS, os.getpid())

    def _monitoring(self, ready_monitoring_clients: list[NamedConnection]) -> None:
        t = time.time()

        for conn in ready_monitoring_clients:
            self.manage_monitoring_clients(conn)

        if self._backend_shutdown_delay is not None:
            active_threads = self.active_threads()

            if active_threads == 0:
                if self._backend_shutdown_timestamp is not None:
                    if time.time() >= self._backend_shutdown_timestamp:
                        self.stop()
            else:
                self._backend_shutdown_timestamp = t + self._backend_shutdown_delay

    def active_threads(self) -> int:
        # Check all threads, if one is active, return True
        # Remove all of the dead ones
        # Make as many passes as necessary
        # with self.adapters_lock:
        while True:
            i = 0
            for k, t in self.adapter_sessions.items():
                if t.is_alive():
                    i += 1
                else:
                    self._remove_session(k)
                    # Break because the dict changed size
                    break
            else:
                # Get out of the loop
                break

        return i

    def _manage_new_adapter_client(self, client: NamedConnection) -> None:
        # Wait for adapter
        # ready = wait([client.conn], timeout=0.1)
        # selectors to work on Unix and Windows
        ready, _, _ = select.select([client.conn], [], [], 0.1)
        if len(ready) == 0:
            client.conn.close()
            return

        try:
            adapter_request = client.conn.recv()
        except EOFError:
            return
        action = Action(adapter_request[0])
        if action == Action.SELECT_ADAPTER:
            adapter_descriptor = adapter_request[1]
            # If the session exists but it is dead, delete it
            if (
                adapter_descriptor in self.adapter_sessions
                and not self.adapter_sessions[adapter_descriptor].is_alive()
            ):
                self._remove_session(adapter_descriptor)

            if adapter_descriptor not in self.adapter_sessions:
                # Create the adapter backend thread
                self._logger.info(f"Creating adapter session for {adapter_descriptor}")
                thread = AdapterSession(
                    adapter_descriptor, shutdown_delay=self._session_shutdown_delay
                )  # TODO : Put another delay here ?
                # with self.adapters_lock:
                thread.start()
                self.adapter_sessions[adapter_descriptor] = thread

            self.adapter_sessions[adapter_descriptor].add_connection(client)
            frontend_send(client.conn, action)
        else:
            client.conn.close()

        self._update_monitoring(adapter_sessions=True)

    def _new_monitoring_client(self, client: NamedConnection) -> None:
        # with self._monitoring_connections_lock:
        self._monitoring_connections.append(client)
        self._update_monitoring(monitoring_sessions=True, stats=True)

    def _new_logger_client(self, client: NamedConnection) -> None:
        # Add connection to the single log handler
        self._log_handler.add_connection(client, self._remove_logger_connection)
        # self._logger_connections.append(client)
        self._update_monitoring(monitoring_sessions=True)

    def _new_adapter_client(self, client: NamedConnection) -> None:
        try:
            role_request = client.conn.recv()
        except EOFError:
            return

        action = Action(role_request[0])
        frontend_send(client.conn, action)

        # Send confirmation directly
        if action == Action.SET_ROLE_ADAPTER:
            self._manage_new_adapter_client(client)
        elif action == Action.SET_ROLE_MONITORING:
            self._new_monitoring_client(client)
        elif action == Action.SET_ROLE_LOGGER:
            self._new_logger_client(client)
        elif action == Action.PING:
            frontend_send(client.conn, Action.PING)
        elif action == Action.STOP:
            self._logger.info("Stop request from client")
            client.conn.close()
            self.stop()
        else:
            frontend_send(client.conn, Action.ERROR_INVALID_ROLE)
            client.conn.close()

    def start(self) -> None:
        while self.running:
            # Use selectors to work on both Linux and Windows

            selectables: list[Selectable] = [
                x.conn for x in self._monitoring_connections
            ]
            selectables.append(self.listener._listener._socket)  # type: ignore

            ready, _, _ = select.select(selectables, [], [], self.MONITORING_DELAY)

            # ready : List[Selectable] = wait( # type: ignore
            #     [self.listener._listener._socket] + [x.conn for x in self._monitoring_connections], # type: ignore
            #     timeout=self.MONITORING_DELAY,
            # )

            if self.listener._listener._socket in ready:  # type: ignore
                conn = self.listener.accept()

                self._new_adapter_client(NamedConnection(conn))
                ready.remove(self.listener._listener._socket)  # type: ignore

            self._monitoring(
                [c for c in self._monitoring_connections if c.conn in ready]
            )

        self.listener.close()
        self._logger.info("Backend stopped")

    def _delayed_stop(self) -> None:
        if self._backend_shutdown_delay is not None:
            self.shutdown_timer: threading.Timer | None = threading.Timer(
                float(self._backend_shutdown_delay), self.stop
            )
            self.shutdown_timer.start()

    def stop(self) -> None:
        self.running = False
        # Open a connection to stop the server
        try:
            # If the listener is on all interfaces, use localhost
            if self.host == "0.0.0.0":  # ALL_ADDRESSES:
                address = LOCALHOST
            else:
                address = self.host
            # Always connect to localhost
            conn = Client((address, self.port))
            frontend_send(conn, Action.STOP)
            conn.close()
        except Exception:
            pass


def main(input_args: list[str] | None = None) -> None:

    argument_parser = argparse.ArgumentParser()

    argument_parser.add_argument(
        "-a",
        "--address",
        type=str,
        default=LOCALHOST,
        help="Listening address, set it to the interface that will be used by the client",
    )
    argument_parser.add_argument("-p", "--port", type=int, default=BACKEND_PORT)
    argument_parser.add_argument(
        "-s",
        "--shutdown-delay",
        type=int,
        default=None,
        help="Delay before the backend shutdowns automatically",
    )
    argument_parser.add_argument("-q", "--quiet", default=False, action="store_true")
    argument_parser.add_argument("-v", "--verbose", default=False, action="store_true")

    args = argument_parser.parse_args(input_args)

    backend = Backend(
        host=args.address, port=args.port, backend_shutdown_delay=args.shutdown_delay
    )
    backend.start()


if __name__ == "__main__":
    main()
