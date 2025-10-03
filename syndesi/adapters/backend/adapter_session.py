# File : backendclient.py
# Author : Sébastien Deriaz
# License : GPL
#
# The backend client manages the link between clients (frontend) and the adapter (backend)
# It is instanctiated by the backend and has a thread to manage incoming data from clients
# as well as read incoming data from the adapter backend

import logging
import threading
import time
from enum import Enum
from multiprocessing.connection import Pipe, wait
from typing import Any

from syndesi.adapters.backend.stop_condition_backend import (
    stop_condition_to_backend,
)
from syndesi.tools.errors import make_error_description
from syndesi.tools.types import NumberLike

from ...tools.backend_api import Action, frontend_send
from ...tools.log_settings import LoggerAlias
from .adapter_backend import (
    AdapterBackend,
    Selectable,
    nmin,
)
from .backend_tools import NamedConnection
from .descriptors import (
    Descriptor,
    IPDescriptor,
    SerialPortDescriptor,
    VisaDescriptor,
    adapter_descriptor_by_string,
)
from .ip_backend import IPBackend
from .serialport_backend import SerialPortBackend

# from .stop_condition_backend import stop_condition_from_list
from .visa_backend import VisaBackend


class TimeoutEvent(Enum):
    MONITORING = 0
    ADAPTER = 1
    # CONNECTIONS = 2


def get_adapter(descriptor: Descriptor) -> AdapterBackend:
    # The adapter doesn't exist, create it
    if isinstance(
        descriptor, SerialPortDescriptor
    ):  # Add mandatory timeout and stop_condition here ?
        return SerialPortBackend(descriptor=descriptor)
    elif isinstance(descriptor, IPDescriptor):
        return IPBackend(descriptor=descriptor)
    elif isinstance(descriptor, VisaDescriptor):
        return VisaBackend(descriptor=descriptor)
    else:
        raise ValueError(f"Unsupported descriptor : {descriptor}")


class AdapterSession(threading.Thread):
    MONITORING_DELAY = 0.5
    daemon = True
    _shutdown_counter_top: int | None
    _shutdown_counter: int | None

    def __init__(self, adapter_descriptor: str, shutdown_delay: NumberLike | None):
        super().__init__(daemon=True)
        self._logger = logging.getLogger(LoggerAlias.ADAPTER_BACKEND.value)
        self._logger.setLevel("DEBUG")
        self._role = None
        self._next_monitoring_timestamp = time.time() + self.MONITORING_DELAY

        # self._stop_flag = False
        self._connections_lock = threading.Lock()
        # self._connection_condition = threading.Condition(self._connections_lock)

        descriptor = adapter_descriptor_by_string(adapter_descriptor)

        self._adapter: AdapterBackend = get_adapter(descriptor)

        self.connections: list[NamedConnection] = []
        # self.connection_names : Dict[NamedConnection] = {}

        # self._new_connection_r, self._new_connection_w = os.pipe()
        # os.pipe does not work on Windows
        self._new_connection_r, self._new_connection_w = Pipe()

        self._shutdown_delay = shutdown_delay
        if self._shutdown_delay is not None:
            self._shutdown_counter_top = int(
                round(self._shutdown_delay / self.MONITORING_DELAY)
            )
            self._shutdown_counter = self._shutdown_counter_top
        else:
            self._shutdown_counter_top = None
            self._shutdown_counter = None

        # self._timeout_events: list[tuple[TimeoutEvent, float]] = []

        self._read_init_id = 0

    def add_connection(self, conn: NamedConnection) -> None:
        with self._connections_lock:
            self.connections.append(conn)
            # os.write(self._new_connection_w, b"\x00")
            self._new_connection_w.send(b"\x00")
            self._logger.info(f"New client : {conn.remote()}")

    def _remove_connection(self, conn: NamedConnection) -> None:
        with self._connections_lock:
            if conn in self.connections:
                conn.conn.close()
                self.connections.remove(conn)

    def send(self, conn: NamedConnection, action: Action, *args: Any) -> None:
        if not frontend_send(conn.conn, action, *args):
            self._logger.warning(f"Failed to send to {conn.remote()}")
            self._remove_connection(conn)

    def send_to_all(self, action: Action, *args: Any) -> None:
        for conn in self.connections:
            frontend_send(conn.conn, action, *args)

    def enumerate_connections(self) -> list[str]:
        return [x.remote_address() for x in self.connections]

    def is_adapter_opened(self) -> bool:
        return self._adapter.is_opened()

    def run(self) -> None:
        while True:
            try:
                stop = self.loop()
                if stop:
                    break
            except Exception as e:
                error_message = make_error_description(e)

                self._logger.critical(
                    f"Error in {self._adapter.descriptor} session loop : {error_message}"
                )
                try:
                    error_message = make_error_description(e)

                    for conn in self.connections:
                        frontend_send(conn.conn, Action.ERROR_GENERIC, error_message)
                except Exception:
                    break
        self._logger.info(f"Exit {self._adapter.descriptor} session loop")

    def loop(self) -> bool:
        # This is the main loop of the session
        # It listens for the following events :
        # - New client
        #   -> asynchronous from backend
        # - Event on a current client connection
        #   -> listen to conn
        # - Adapter event
        #   -> listen to socket/fd
        # The wait has a timeout set by the adapter, it corresponds to the current continuation/total timeout

        # Create a list of what is awaited
        wait_list: list[Selectable] = [conn.conn for conn in self.connections]
        adapter_fd = self._adapter.selectable()
        if adapter_fd is not None and adapter_fd.fileno() >= 0:
            wait_list.append(adapter_fd)

        wait_list.append(self._new_connection_r)

        timeout_timestamp = None
        event = None

        adapter_timestamp = self._adapter.get_next_timeout()
        if adapter_timestamp is not None:
            timeout_timestamp = nmin(timeout_timestamp, adapter_timestamp)
            event = TimeoutEvent.ADAPTER

        if (
            timeout_timestamp is None
            or self._next_monitoring_timestamp < timeout_timestamp
        ):
            timeout_timestamp = self._next_monitoring_timestamp
            event = TimeoutEvent.MONITORING

        if timeout_timestamp is None:
            timeout = None
        else:
            timeout = timeout_timestamp - time.time()
        ready = wait(wait_list, timeout=timeout)  # type: ignore
        t = time.time()
        if len(ready) == 0:
            # Timeout event
            if event == TimeoutEvent.MONITORING:
                self._next_monitoring_timestamp = t + self.MONITORING_DELAY
                stop = self._monitor()
                if stop:
                    return True
            elif event == TimeoutEvent.ADAPTER:
                signal = self._adapter.on_timeout_event()
                if signal is not None:
                    # The signal can be none if it has been disabled in the meantime
                    self._logger.debug(f"Adapter signal (timeout) : {signal}")
                    self.send_to_all(Action.ADAPTER_SIGNAL, signal)

        # Main adapter loop
        if self._new_connection_r in ready:
            # New connection event
            self._new_connection_r.recv()
        # Adapter event
        if self._adapter.selectable() in ready:
            for signal in self._adapter.on_socket_ready():
                self._logger.debug(f"Adapter signal (selectable) : {signal}")
                self.send_to_all(Action.ADAPTER_SIGNAL, signal)

        for conn in self.connections:
            if conn.conn in ready:
                # Manage a command received from the user
                self.manage_conn(conn)
        return False

    def _monitor(self) -> bool:
        stop = False
        if self._shutdown_counter is not None:
            with self._connections_lock:
                if len(self.connections) == 0:
                    if self._shutdown_counter == 0:
                        # Shutdown
                        self._logger.info(
                            f"No clients on adapter {self._adapter.descriptor} for {self._shutdown_delay}s, closing"
                        )
                        self._adapter.close()
                        stop = True
                    else:
                        self._shutdown_counter -= 1
                else:
                    self._shutdown_counter = self._shutdown_counter_top

        return stop

    def manage_conn(self, conn: NamedConnection) -> None:
        extra_arguments: tuple[Any, ...]
        remove_after_response = False
        if not conn.conn.poll():
            # No data, connection is closed
            self._logger.warning(f"Client {conn.remote()} closed unexpectedly")
            self._remove_connection(conn)
            return
        try:
            request = conn.conn.recv()
        except (EOFError, ConnectionResetError) as e:
            # Probably a ping or an error
            self._logger.warning(
                f"Failed to read from client {conn.remote()} ({e}), closing connection "
            )
            self._remove_connection(conn)
        else:
            if not (isinstance(request, tuple) and len(request) >= 1):
                response_action = Action.ERROR_INVALID_REQUEST
                extra_arguments = ("",)
            else:
                action: Action
                action = Action(request[0])
                response_action = Action.ERROR_GENERIC
                extra_arguments = ("Unknown error in session",)
                try:
                    match action:
                        case Action.OPEN:
                            self._adapter.set_stop_conditions(
                                [stop_condition_to_backend(sc) for sc in request[1]]
                            )
                            if self._adapter.open():
                                # Success !
                                response_action = Action.OPEN
                            else:
                                response_action = Action.ERROR_FAILED_TO_OPEN
                            extra_arguments = ("",)
                        case Action.WRITE:
                            data = request[1]
                            if self._adapter.is_opened():
                                if self._adapter.write(data):
                                    # Success
                                    response_action, extra_arguments = Action.WRITE, ()
                                else:
                                    response_action, extra_arguments = (
                                        Action.ERROR_ADAPTER_DISCONNECTED,
                                        ("",),
                                    )
                                    # TODO : Maybe close here ? not sure
                            else:
                                response_action, extra_arguments = (
                                    Action.ERROR_ADAPTER_NOT_OPENED,
                                    ("Open adapter before writing",),
                                )
                                self._logger.error("Could not write, adapter is closed")
                        case Action.PING:
                            response_action, extra_arguments = Action.PING, ()
                        case Action.SET_STOP_CONDITIONs:
                            self._adapter.set_stop_conditions(
                                [stop_condition_to_backend(sc) for sc in request[1]]
                            )
                            response_action, extra_arguments = (
                                Action.SET_STOP_CONDITIONs,
                                (),
                            )
                        case Action.FLUSHREAD:
                            self._adapter.flush_read()
                            response_action, extra_arguments = Action.FLUSHREAD, ()
                        case Action.START_READ:
                            response_time = float(request[1])
                            self._adapter.start_read(response_time, self._read_init_id)
                            response_action, extra_arguments = Action.START_READ, (
                                self._read_init_id,
                            )
                            self._read_init_id += 1

                        # case Action.GET_BACKEND_TIME:
                        #     response_action = Action.GET_BACKEND_TIME
                        #     extra_arguments = (request_timestamp, )
                        case Action.CLOSE:
                            force = request[1]
                            # Close this connection
                            remove_after_response = True
                            response_action, extra_arguments = Action.CLOSE, ()
                            if force:
                                self._adapter.close()
                        case _:
                            response_action, extra_arguments = (
                                Action.ERROR_UNKNOWN_ACTION,
                                (f"{action}",),
                            )
                except Exception as e:
                    error_message = make_error_description(e)

                    response_action, extra_arguments = (
                        Action.ERROR_GENERIC,
                        (error_message,),
                    )

            frontend_send(conn.conn, response_action, *extra_arguments)
            if remove_after_response:
                self._logger.info(f"Closing client {conn.remote()} connection")
                self._remove_connection(conn)
