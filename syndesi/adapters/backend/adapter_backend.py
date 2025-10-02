# File : adapterbackend.py
# Author : Sébastien Deriaz
# License : GPL
#
# The adapter backend is the background class that manages communication
# with one particular device. It is always instanciated in a backend client

import logging
import socket
import time
from abc import ABC, abstractmethod
from collections.abc import Generator
from dataclasses import dataclass
from enum import Enum
from multiprocessing.connection import Connection
from threading import Thread
from typing import Protocol

from ...tools.backend_api import AdapterBackendStatus, Fragment
from ...tools.log_settings import LoggerAlias
from ..stop_condition import StopConditionType
from .descriptors import Descriptor
from .stop_condition_backend import (
    ContinuationBackend,
    StopConditionBackend,
    TotalBackend,
)


class HasFileno(Protocol):
    def fileno(self) -> int:
        return -1


Selectable = HasFileno | int

DEFAULT_STOP_CONDITION = None


class SocketReadException(Exception):
    pass


# STOP_DESIGNATORS = {
#     # "timeout": {
#     #     TimeoutType.RESPONSE: "TR",
#     #     TimeoutType.CONTINUATION: "TC",
#     #     TimeoutType.TOTAL: "TT",
#     # },
#     "stop_condition": {TerminationBackend: "ST", LengthBackend: "SL"},
#     "previous-buffer": "PB",
# }


class Origin(Enum):
    TIMEOUT = "timeout"
    STOP_CONDITION = "stop_condition"


class AdapterSignal:
    pass


class AdapterDisconnected(AdapterSignal):
    def __str__(self) -> str:
        return "Adapter disconnected"

    def __repr__(self) -> str:
        return self.__str__()


# @dataclass
# class AdapterReadInit(AdapterSignal):
#     end_delay : float | None

#     def __str__(self) -> str:
#         return f"Read init (end delay : {self.end_delay})"

#     def __repr__(self) -> str:
#         return self.__str__()


@dataclass
class AdapterResponseTimeout(AdapterSignal):
    identifier: int

    def __str__(self) -> str:
        return "Response timeout"

    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class AdapterReadPayload(AdapterSignal):
    fragments: list[Fragment]
    stop_timestamp: float
    stop_condition_type: StopConditionType
    previous_read_buffer_used: bool
    response_timestamp: float | None
    # Only used by client and set by frontend
    response_delay: float | None = None

    def data(self) -> bytes:
        return b"".join([f.data for f in self.fragments])

    def __str__(self) -> str:
        return f"Read payload : {self.data()!r}"

    def __repr__(self) -> str:
        return self.__str__()


# This class holds a request made by the client to know if a response
# is received without the specified time frame
@dataclass
class ResponseRequest:
    timestamp: float
    identifier: int


def nmin(a: float | None, b: float | None) -> float | None:
    if a is None and b is None:
        return None
    elif a is None:
        return b
    elif b is None:
        return a
    else:
        return min(a, b)


class AdapterBackend(ABC):
    class ThreadCommands(Enum):
        STOP = b"0"

    class AdapterTimeoutEventOrigin(Enum):
        TIMEOUT = 0
        RESPONSE_REQUEST = 1

    def __init__(self, descriptor: Descriptor) -> None:
        """
        Adapter instance

        Parameters
        ----------
        timeout : float or Timeout instance
            Default timeout is Timeout(response=5, continuation=0.2, total=None)
        stop_condition : StopCondition or None
            Default to None
        """
        self._logger = logging.getLogger(LoggerAlias.ADAPTER_BACKEND.value)

        super().__init__()

        # TODO : Switch to multiple stop conditios
        self._stop_conditions: list[StopConditionBackend] = [
            ContinuationBackend(time=0.1)
        ]
        self.descriptor = descriptor
        self._thread: Thread | None = None
        self._status = AdapterBackendStatus.DISCONNECTED
        self._thread_commands_read, self._thread_commands_write = socket.socketpair()
        self.backend_signal: Connection | None = None
        self.fragments: list[Fragment] = []
        self._next_timeout_timestamp: float | None = None
        # _response_time indicates if the frontend asked for a read
        # None : No ask
        # float : Ask for a response to happen at the specified value at max
        self._response_request: ResponseRequest | None = None
        self._response_request_start: float | None = None

        self._first_fragment = True

        # Buffer for data that has been pulled from the queue but
        # not used because of termination or length stop condition
        self._previous_buffer = Fragment(b"", None)

        self._last_write_time = time.time()

    def set_stop_conditions(self, stop_conditions: list[StopConditionBackend]) -> None:
        """
        Overwrite the stop-condition

        Parameters
        ----------
        stop_condition : StopCondition
        """
        self._stop_conditions = stop_conditions

    def flush_read(self) -> bool:
        """
        Flush the input buffer
        """
        self._logger.debug("Flush")
        self._previous_buffer = Fragment(b"", None)
        self._response_request = None
        self.fragments = []
        for stop_condition in self._stop_conditions:
            stop_condition.flush_read()
        return True

    def previous_read_buffer_empty(self) -> bool:
        """
        Check whether the previous read buffer is empty

        Returns
        -------
        empty : bool
        """
        return self._previous_buffer.data == b""

    @abstractmethod
    def open(self) -> bool:
        """
        Start communication with the device
        """
        pass

    def close(self) -> bool:
        """
        Stop communication with the device
        """
        self._status = AdapterBackendStatus.DISCONNECTED
        return True

    def write(self, data: bytes) -> bool:
        """
        Send data to the device

        Parameters
        ----------
        data : bytes or str
        """
        self._last_write_time = time.time()
        self._logger.debug(f"Write {repr(data)}")
        return True

    @abstractmethod
    def selectable(self) -> HasFileno | None:
        """
        Return an object with a fileno() method (e.g., socket, Connection) suitable for use with select/poll.
        """
        raise NotImplementedError

    @abstractmethod
    def _socket_read(self) -> Fragment:
        raise NotImplementedError

    def _fragments_to_string(self, fragments: list[Fragment]) -> str:
        if len(fragments) > 0:
            return "+".join(repr(f.data) for f in fragments)
        else:
            return str([])

    def on_socket_ready(self) -> Generator[AdapterSignal, None, None]:
        fragment = self._socket_read()
        if fragment.timestamp is not None and self._last_write_time is not None:
            fragment_delta_t = fragment.timestamp - self._last_write_time
        else:
            fragment_delta_t = float("nan")
        if fragment.data == b"":
            self.close()
            yield AdapterDisconnected()
        else:
            self._logger.debug(
                f"New fragment {fragment_delta_t:+.3f} {fragment}"
                + (" (first)" if self._first_fragment else "")
            )
            if self._status == AdapterBackendStatus.CONNECTED:
                t = time.time()

                # If there's a response request, disable it if there's a timeout stop condition
                # The stop-condition will do the job

                if self._response_request is not None:
                    for stop_condition in self._stop_conditions:
                        if isinstance(
                            stop_condition, (ContinuationBackend, TotalBackend)
                        ):
                            self._response_request = None
                            break

                while True:
                    if self._first_fragment:
                        self._first_fragment = False
                        self._read_start_timestamp = t
                        for stop_condition in self._stop_conditions:
                            stop_condition.initiate_read()

                    stop = False
                    kept = fragment

                    # Run each stop condition one after the other, if a stop is reached, stop evaluating
                    stop_condition_type: StopConditionType
                    for stop_condition in self._stop_conditions:
                        (
                            stop,
                            kept,
                            self._previous_buffer,
                            self._next_timeout_timestamp,
                        ) = stop_condition.evaluate(kept)
                        if stop:
                            stop_condition_type = stop_condition.type()
                            break

                    # if kept.data != b'':
                    #     self.fragments.append(kept)

                    self.fragments.append(kept)

                    if stop:
                        self._first_fragment = True
                        self._logger.debug(
                            f"Payload {self._fragments_to_string(self.fragments)} ({stop_condition_type.value})"
                        )
                        if (
                            self._response_request_start is None
                            or len(self.fragments) == 0
                        ):
                            response_delay = None
                        else:
                            if self.fragments[0].timestamp is None:
                                response_delay = None
                            else:
                                response_delay = (
                                    self.fragments[0].timestamp
                                    - self._response_request_start
                                )
                            self._response_request_start = None
                        yield AdapterReadPayload(
                            fragments=self.fragments,
                            stop_timestamp=t,
                            stop_condition_type=stop_condition_type,
                            previous_read_buffer_used=False,
                            response_timestamp=self.fragments[0].timestamp,
                            response_delay=response_delay,
                        )
                        self._next_timeout_timestamp = None  # Experiment !
                        self.fragments.clear()

                    if len(self._previous_buffer.data) > 0 and stop:
                        # If there's a previous buffer, put it in the fragment and loop again
                        # Only loop if there's a stop (oterwise a stop would never happen again)
                        fragment = self._previous_buffer

                    else:
                        # If not, quit now
                        break

        return None

    def start_read(self, response_time: float, identifier: int) -> None:
        """
        Start a read operation. This is a signal from the frontend. The only goal is to set the response time
        and tell the frontend if nothing arrives within a set time
        """
        self._response_request_start = time.time()
        self._logger.debug(f"Setup read [{identifier}] in {response_time:.3f} s")
        self._response_request = ResponseRequest(
            self._response_request_start + response_time, identifier
        )

    @abstractmethod
    def is_opened(self) -> bool:
        """
        Return True if adapter is opened, False otherwise
        """

    def __str__(self) -> str:
        return self.descriptor.__str__()

    def __repr__(self) -> str:
        return self.__str__()

    def on_timeout_event(self) -> AdapterSignal | None:
        t = time.time()

        if self._next_timeout_origin == self.AdapterTimeoutEventOrigin.TIMEOUT:
            self._next_timeout_timestamp = None
            self._first_fragment = True
            if self._response_request_start is None or len(self.fragments) == 0:
                response_delay = None
            else:
                if self.fragments[0].timestamp is not None:
                    response_delay = (
                        self.fragments[0].timestamp - self._response_request_start
                    )
                else:
                    response_delay = None
                self._response_request_start = None

            output = AdapterReadPayload(
                stop_timestamp=t,
                stop_condition_type=StopConditionType.TIMEOUT,
                previous_read_buffer_used=False,
                fragments=self.fragments,
                response_timestamp=(
                    self.fragments[0].timestamp if len(self.fragments) > 0 else None
                ),
                response_delay=response_delay,
            )
            # Reset response request
            if self._response_request is not None:
                self._response_request = None
                self._response_request_start = None
            # Clear all of the fragments
            self.fragments = []
            return output

        elif (
            self._next_timeout_origin == self.AdapterTimeoutEventOrigin.RESPONSE_REQUEST
        ):
            if self._response_request is not None:
                signal = AdapterResponseTimeout(self._response_request.identifier)
                self._response_request = None
                return signal

        return None

    def get_next_timeout(self) -> float | None:
        min_timestamp = None
        self._next_timeout_origin = None

        if self._next_timeout_timestamp is not None:
            min_timestamp = self._next_timeout_timestamp
            self._next_timeout_origin = self.AdapterTimeoutEventOrigin.TIMEOUT

        if self._response_request is not None:
            if (
                min_timestamp is None
                or self._response_request.timestamp < min_timestamp
            ):
                min_timestamp = self._response_request.timestamp
                self._next_timeout_origin = (
                    self.AdapterTimeoutEventOrigin.RESPONSE_REQUEST
                )
        return min_timestamp
