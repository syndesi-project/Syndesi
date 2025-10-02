# File : adapters.py
# Author : Sébastien Deriaz
# License : GPL
#
# Adapters provide a common abstraction for the media layers (physical + data link + network)
# The following classes are provided, which all are derived from the main Adapter class
#   - IP
#   - Serial
#   - VISA
#
# Note that technically VISA is not part of the media layer, only USB is.
# This is a limitation as it is to this day not possible to communicate "raw"
# with a device through USB yet
#
# An adapter is meant to work with bytes objects but it can accept strings.
# Strings will automatically be converted to bytes using utf-8 encoding

import logging
import os
import queue
import subprocess
import sys
import threading
import time
import weakref
from abc import ABC, abstractmethod
from collections.abc import Callable
from enum import Enum
from multiprocessing.connection import Client, Connection
from types import EllipsisType
from typing import Any

from syndesi.tools.types import NumberLike, is_number

from ..tools.backend_api import (
    BACKEND_PORT,
    EXTRA_BUFFER_RESPONSE_TIME,
    Action,
    BackendResponse,
    Fragment,
    default_host,
    raise_if_error,
)
from ..tools.log_settings import LoggerAlias
from .backend.adapter_backend import (
    AdapterDisconnected,
    AdapterReadPayload,
    AdapterResponseTimeout,
    AdapterSignal,
)
from .backend.backend_tools import BACKEND_REQUEST_DEFAULT_TIMEOUT
from .backend.descriptors import Descriptor
from .stop_condition import Continuation, StopCondition, StopConditionType
from .timeout import Timeout, TimeoutAction, any_to_timeout

DEFAULT_STOP_CONDITION = Continuation(time=0.1)

DEFAULT_TIMEOUT = Timeout(response=5, action="error")

# Maximum time to let the backend start
START_TIMEOUT = 2
# Time to shutdown the backend
SHUTDOWN_DELAY = 2


class SignalQueue(queue.Queue[AdapterSignal]):
    def __init__(self) -> None:
        self._read_payload_counter = 0
        super().__init__(0)

    def has_read_payload(self) -> bool:
        return self._read_payload_counter > 0

    def put(
        self, signal: AdapterSignal, block: bool = True, timeout: float | None = None
    ) -> None:
        if isinstance(signal, AdapterReadPayload):
            self._read_payload_counter += 1
        return super().put(signal, block, timeout)

    def get(self, block: bool = True, timeout: float | None = None) -> AdapterSignal:
        signal = super().get(block, timeout)
        if isinstance(signal, AdapterReadPayload):
            self._read_payload_counter -= 1
        return signal


def is_backend_running(address: str, port: int) -> bool:

    try:
        conn = Client((address, port))
    except ConnectionRefusedError:
        return False
    else:
        conn.close()
        return True


def start_backend(port: int | None = None) -> None:
    arguments = [
        sys.executable,
        "-m",
        "syndesi.adapters.backend.backend",
        "-s",
        str(SHUTDOWN_DELAY),
        "-q",
        "-p",
        str(BACKEND_PORT if port is None else port),
    ]

    stdin = subprocess.DEVNULL
    stdout = subprocess.DEVNULL
    stderr = subprocess.DEVNULL

    if os.name == "posix":
        subprocess.Popen(
            arguments,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
            close_fds=True,
        )

    else:
        # Windows: detach from the parent's console so keyboard Ctrl+C won't propagate.
        CREATE_NEW_PROCESS_GROUP = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore
        DETACHED_PROCESS = 0x00000008  # not exposed by subprocess on all Pythons
        # Optional: CREATE_NO_WINDOW (no window even for console apps)
        CREATE_NO_WINDOW = 0x08000000

        creationflags = CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS | CREATE_NO_WINDOW

        subprocess.Popen(
            arguments,
            stdin=stdin,
            stdout=stdout,
            stderr=stderr,
            creationflags=creationflags,
            close_fds=True,
        )


class ReadScope(Enum):
    NEXT = "next"
    BUFFERED = "buffered"


class Adapter(ABC):
    def __init__(
        self,
        descriptor: Descriptor,
        alias: str = "",
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        timeout: Timeout | EllipsisType | NumberLike | None = ...,
        encoding: str = "utf-8",
        event_callback: Callable[[AdapterSignal], None] | None = None,
        auto_open: bool = True,
        backend_address: str | None = None,
        backend_port: int | None = None,
    ) -> None:
        """
        Adapter instance

        Parameters
        ----------
        alias : str
            The alias is used to identify the class in the logs
        timeout : float or Timeout instance
            Default timeout is
        stop_condition : StopCondition or None
            Default to None
        encoding : str
            Which encoding to use if str has to be encoded into bytes
        """
        self._init_ok = False
        super().__init__()
        self._logger = logging.getLogger(LoggerAlias.ADAPTER.value)
        self.encoding = encoding
        self._signal_queue: SignalQueue = SignalQueue()
        self.event_callback: Callable[[AdapterSignal], None] | None = event_callback
        self.backend_connection: Connection | None = None
        self._backend_connection_lock = threading.Lock()
        self._make_backend_request_queue: queue.Queue[BackendResponse] = queue.Queue()
        self._make_backend_request_flag = threading.Event()
        self.opened = False
        self._alias = alias

        if backend_address is None:
            self._backend_address = default_host
        else:
            self._backend_address = backend_address
        if backend_port is None:
            self._backend_port = BACKEND_PORT
        else:
            self._backend_port = backend_port

        # There a two possibilities here
        # A) The descriptor is fully initialized
        #    -> The adapter can be connected directly
        # B) The descriptor is not fully initialized
        #    -> Wait for the protocol to set defaults and then connect the adapter

        assert isinstance(
            descriptor, Descriptor
        ), "descriptor must be a Descriptor class"
        self.descriptor = descriptor
        self.auto_open = auto_open

        # Set the stop-condition
        self._stop_conditions: list[StopCondition]
        if stop_conditions is ...:
            self._default_stop_condition = True
            self._stop_conditions = [DEFAULT_STOP_CONDITION]
        else:
            self._default_stop_condition = False
            if isinstance(stop_conditions, StopCondition):
                self._stop_conditions = [stop_conditions]
            elif isinstance(stop_conditions, list):
                self._stop_conditions = stop_conditions
            else:
                raise ValueError("Invalid stop_conditions")

        # Set the timeout
        self.is_default_timeout = False
        self._timeout: Timeout | None
        if timeout is Ellipsis:
            # Not set
            self.is_default_timeout = True
            self._timeout = DEFAULT_TIMEOUT
        elif isinstance(timeout, Timeout):
            self._timeout = timeout
        elif is_number(timeout):
            self._timeout = Timeout(timeout, action=TimeoutAction.ERROR)
        elif timeout is None:
            self._timeout = timeout

        # Buffer for data that has been pulled from the queue but
        # not used because of termination or length stop condition
        self._previous_buffer = b""

        if self.descriptor.is_initialized():
            self.connect()

        weakref.finalize(self, self._cleanup)
        self._init_ok = True

        # We can auto-open only if auto_open is enabled and if
        # connection with the backend has been made (descriptor initialized)
        if self.auto_open and self.backend_connection is not None:
            self.open()

    def connect(self) -> None:
        if self.backend_connection is not None:
            # No need to connect, everything has been done already
            return
        if not self.descriptor.is_initialized():
            raise RuntimeError("Descriptor wasn't initialized fully")

        if is_backend_running(self._backend_address, self._backend_port):
            self._logger.info("Backend already running")
        else:
            self._logger.info("Starting backend...")
            start_backend(self._backend_port)
            start = time.time()
            while time.time() < (start + START_TIMEOUT):
                if is_backend_running(self._backend_address, self._backend_port):
                    self._logger.info("Backend started")
                    break
                time.sleep(0.1)
            else:
                # Backend could not start
                self._logger.error("Could not start backend")

        # Create the client to communicate with the backend
        try:
            self.backend_connection = Client((default_host, BACKEND_PORT))
        except ConnectionRefusedError as err:
            raise RuntimeError("Failed to connect to backend") from err
        self._read_thread = threading.Thread(
            target=self.read_thread,
            args=(self._signal_queue, self._make_backend_request_queue),
            daemon=True,
        )
        self._read_thread.start()

        # Identify ourselves
        self._make_backend_request(Action.SET_ROLE_ADAPTER)

        # Set the adapter
        self._make_backend_request(Action.SELECT_ADAPTER, str(self.descriptor))

        if self.auto_open:
            self.open()

    def _make_backend_request(self, action: Action, *args: Any) -> BackendResponse:
        """
        Send a request to the backend and return the arguments
        """

        with self._backend_connection_lock:
            if self.backend_connection is not None:
                self.backend_connection.send((action.value, *args))

        self._make_backend_request_flag.set()
        try:
            response = self._make_backend_request_queue.get(
                timeout=BACKEND_REQUEST_DEFAULT_TIMEOUT
            )
        except queue.Empty as err:
            raise RuntimeError(
                f"Failed to receive response from backend to {action}"
            ) from err

        assert (
            isinstance(response, tuple) and len(response) > 0
        ), f"Invalid response received from backend : {response}"
        raise_if_error(response)

        return response[1:]

    def read_thread(
        self,
        signal_queue: SignalQueue,
        request_queue: queue.Queue[BackendResponse],
    ) -> None:
        while True:
            try:
                if self.backend_connection is None:
                    raise RuntimeError("Backend connection wasn't initialized")
                response: tuple[Any, ...] = self.backend_connection.recv()
            except (EOFError, TypeError, OSError):
                signal_queue.put(AdapterDisconnected())
                request_queue.put((Action.ERROR_BACKEND_DISCONNECTED,))
                break
            else:
                if not isinstance(response, tuple):
                    raise RuntimeError(f"Invalid response from backend : {response}")
                action = Action(response[0])

                if action == Action.ADAPTER_SIGNAL:
                    # if is_event(action):
                    if len(response) <= 1:
                        raise RuntimeError(f"Invalid event response : {response}")
                    signal: AdapterSignal = response[1]
                    if self.event_callback is not None:
                        self.event_callback(signal)
                    signal_queue.put(signal)
                else:
                    request_queue.put(response)

    @abstractmethod
    def _default_timeout(self) -> Timeout:
        pass

    def set_timeout(self, timeout: Timeout | None) -> None:
        """
        Overwrite timeout

        Parameters
        ----------
        timeout : Timeout
        """
        self._timeout = timeout

    def set_default_timeout(self, default_timeout: Timeout | None) -> None:
        """
        Set the default timeout for this adapter. If a previous timeout has been set, it will be fused

        Parameters
        ----------
        default_timeout : Timeout or tuple or float
        """
        if self.is_default_timeout:
            self._logger.debug(f"Setting default timeout to {default_timeout}")
            self._timeout = default_timeout

    def set_stop_conditions(
        self, stop_conditions: StopCondition | None | list[StopCondition]
    ) -> None:
        """
        Overwrite the stop-condition

        Parameters
        ----------
        stop_condition : StopCondition
        """
        if isinstance(stop_conditions, list):
            self._stop_conditions = stop_conditions
        elif isinstance(stop_conditions, StopCondition):
            self._stop_conditions = [stop_conditions]
        elif stop_conditions is None:
            self._stop_conditions = []

        self._make_backend_request(Action.SET_STOP_CONDITIONs, self._stop_conditions)

    def set_default_stop_condition(self, stop_condition: StopCondition) -> None:
        """
        Set the default stop condition for this adapter.

        Parameters
        ----------
        stop_condition : StopCondition
        """
        if self._default_stop_condition:
            self.set_stop_conditions(stop_condition)

    def flushRead(self) -> None:
        """
        Flush the input buffer
        """
        self._make_backend_request(
            Action.FLUSHREAD,
        )
        while True:
            try:
                self._signal_queue.get(block=False)
            except queue.Empty:
                break

    def previous_read_buffer_empty(self) -> bool:
        """
        Check whether the previous read buffer is empty

        Returns
        -------
        empty : bool
        """
        return self._previous_buffer == b""

    def open(self) -> None:
        """
        Start communication with the device
        """
        self._make_backend_request(Action.OPEN, self._stop_conditions)
        self._logger.info("Adapter opened")
        self.opened = True

    def close(self, force: bool = False) -> None:
        """
        Stop communication with the device
        """
        if force:
            self._logger.debug("Closing adapter frontend")
        else:
            self._logger.debug("Force closing adapter backend")
        self._make_backend_request(Action.CLOSE, force)

        with self._backend_connection_lock:
            if self.backend_connection is not None:
                self.backend_connection.close()

        self.opened = False

    def write(self, data: bytes | str) -> None:
        """
        Send data to the device

        Parameters
        ----------
        data : bytes or str
        """

        if isinstance(data, str):
            data = data.encode(self.encoding)
        self._make_backend_request(Action.WRITE, data)

    def read_detailed(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> AdapterReadPayload:
        """
        Read data from the device

        Parameters
        ----------
        timeout : tuple, Timeout
            Temporary timeout
        stop_condition : StopCondition
            Temporary stop condition
        scope : str
            Return previous data ('buffered') or only future data ('next')
        Returns
        -------
        data : bytes
        signal : AdapterReadPayload
        """
        _scope = ReadScope(scope)
        output_signal = None
        read_timeout = None

        if timeout is ...:
            read_timeout = self._timeout
        else:
            read_timeout = any_to_timeout(timeout)

        if read_timeout is None:
            raise RuntimeError("Cannot read without setting a timeout")

        if stop_conditions is not ...:
            if isinstance(stop_conditions, StopCondition):
                stop_conditions = [stop_conditions]
            self._make_backend_request(Action.SET_STOP_CONDITIONs, stop_conditions)

        # First, we check if data is in the buffer and if the scope if set to BUFFERED
        while _scope == ReadScope.BUFFERED and self._signal_queue.has_read_payload():
            signal = self._signal_queue.get()
            if isinstance(signal, AdapterReadPayload):
                output_signal = signal
                break
            # TODO : Implement disconnect ?
        else:
            # Nothing was found, ask the backend with a START_READ request. The backend will
            # respond at most after the response_time with either data or a RESPONSE_TIMEOUT

            if not read_timeout.is_initialized():
                raise RuntimeError("Timeout needs to be initialized")

            _response = read_timeout.response()

            read_init_time = time.time()
            start_read_id = self._make_backend_request(Action.START_READ, _response)[0]

            if _response is None:
                # Wait indefinitely
                read_stop_timestamp = None
            else:
                # Wait for the response time + a bit more
                read_stop_timestamp = read_init_time + _response

            while True:
                try:
                    if read_stop_timestamp is None:
                        queue_timeout = None
                    else:
                        queue_timeout = max(
                            0,
                            read_stop_timestamp
                            - time.time()
                            + EXTRA_BUFFER_RESPONSE_TIME,
                        )

                    signal = self._signal_queue.get(timeout=queue_timeout)
                except queue.Empty as e:
                    raise RuntimeError("Failed to receive response from backend") from e
                if isinstance(signal, AdapterReadPayload):
                    output_signal = signal
                    break
                elif isinstance(signal, AdapterDisconnected):
                    raise RuntimeError("Adapter disconnected")
                elif isinstance(signal, AdapterResponseTimeout):
                    if start_read_id == signal.identifier:
                        output_signal = None
                        break
                    # Otherwise ignore it

        if output_signal is None:
            match read_timeout.action:
                case TimeoutAction.RETURN_EMPTY:
                    t = time.time()
                    return AdapterReadPayload(
                        fragments=[Fragment(b"", t)],
                        stop_timestamp=t,
                        stop_condition_type=StopConditionType.TIMEOUT,
                        previous_read_buffer_used=False,
                        response_timestamp=None,
                        response_delay=None,
                    )
                case TimeoutAction.ERROR:
                    raise TimeoutError(
                        f"No response received from device within {read_timeout.response()} seconds"
                    )
                case _:
                    raise NotImplementedError()

        else:
            return output_signal

    def read(
        self,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> bytes:
        signal = self.read_detailed(timeout=timeout, stop_conditions=stop_conditions)
        return signal.data()

    def _cleanup(self) -> None:
        if self._init_ok and self.opened:
            self.close()

    def query_detailed(
        self,
        data: bytes | str,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> AdapterReadPayload:
        """
        Shortcut function that combines
        - flush_read
        - write
        - read
        """
        self.flushRead()
        self.write(data)
        return self.read_detailed(timeout=timeout, stop_conditions=stop_conditions)

    def query(
        self,
        data: bytes | str,
        timeout: Timeout | EllipsisType | None = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> bytes:
        signal = self.query_detailed(
            data=data, timeout=timeout, stop_conditions=stop_conditions
        )
        return signal.data()

    def set_event_callback(self, callback: Callable[[AdapterSignal], None]) -> None:
        self.event_callback = callback

    def __str__(self) -> str:
        return str(self.descriptor)

    def __repr__(self) -> str:
        return self.__str__()
