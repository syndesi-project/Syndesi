# File : visa.py
# Author : Sébastien Deriaz
# License : GPL

"""
VISA adatper, uses a VISA backend like pyvisa-py or NI to communicate with instruments
"""

import queue
import re
import socket
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from types import EllipsisType
from typing import cast

import pyvisa
from pyvisa.resources import MessageBasedResource

from syndesi.adapters.adapter_worker import (
    AdapterEvent,
    HasFileno,
)
from syndesi.adapters.stop_conditions import Continuation, Fragment, StopCondition
from syndesi.component import Descriptor
from syndesi.tools.errors import AdapterReadError

from .adapter import Adapter
from .timeout import Timeout


class QueueEvent:
    """VISA adapter queue event"""


class DisconnectedEvent(QueueEvent):
    """VISA queue disconnected event"""


@dataclass
class FragmentEvent(QueueEvent):
    """VISA queue new fragment event"""

    fragment: Fragment


@dataclass
class VisaDescriptor(Descriptor):
    """
    VISA descriptor

    ## Examples

    - GPIB (IEEE-488) ``GPIB0::14::INSTR``
    - Serial (RS-232 or USB-Serial)
        - Windows COM1 : ``ASRL1::INSTR``
        - UNIX USB 0 : ``ASRL/dev/ttyUSB0::INSTR``
    - TCPIP INSTR (LXI/VXI-11/HiSLIP-compatible instruments)
        - ``TCPIP0::192.168.1.100::INSTR``
        - ``TCPIP0::my-scope.local::inst0::INSTR``
    - TCPIP SOCKET (Raw TCP communication) ``TCPIP0::192.168.1.42::5025::SOCKET``
    - USB (USBTMC-compliant instruments) ``USB0::0x0957::0x1796::MY12345678::INSTR``
    - VXI (Legacy modular instruments) ``VXI0::2::INSTR``
    - PXI (Modular instrument chassis) ``PXI0::14::INSTR``
    """

    DETECTION_PATTERN = (
        r"([A-Z]+)(\d*|\/[^:]+)?::([^:]+)(?:::([^:]+))?"
        + "(?:::([^:]+))?(?:::([^:]+))?::(INSTR|SOCKET)"
    )

    descriptor: str

    class Interface(Enum):
        """
        VISA Interface
        """

        GPIB = "GPIB"
        SERIAL = "ASRL"
        TCP = "TCPIP"
        USB = "USB"
        VXI = "VXI"
        PXI = "PXI"

    @staticmethod
    def from_string(string: str) -> "VisaDescriptor":
        """
        Create a VISA interface from a string
        """
        if re.match(VisaDescriptor.DETECTION_PATTERN, string):
            return VisaDescriptor(descriptor=string)

        raise ValueError(f"Could not parse descriptor : {string}")

    def __str__(self) -> str:
        return str(self.descriptor)

    def is_initialized(self) -> bool:
        return True


# pylint: disable=too-many-instance-attributes
class Visa(Adapter):
    """
    VISA Adapter, allows for communication with VISA-compatible devices.
    It uses pyvisa under the hood
    """

    THREAD_STOP_DELAY = 0.2

    def __init__(
        self,
        descriptor: str,
        *,
        alias: str = "",
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        timeout: None | float | Timeout | EllipsisType = ...,
        encoding: str = "utf-8",
        event_callback: Callable[[AdapterEvent], None] | None = None,
        auto_open: bool = False,
    ) -> None:

        self._worker_descriptor: VisaDescriptor
        self._descriptor: VisaDescriptor

        if pyvisa is None:
            raise ImportError(
                "Missing optional dependency 'pyvisa'. Install with:\n"
                "  python -m pip install pyvisa"
            )

        self._rm = pyvisa.ResourceManager()
        self._inst: MessageBasedResource | None = (
            None  # annotation only; no runtime import needed
        )

        # We need a socket pair because VISA doesn't expose a selectable fileno/socket
        # So we create a thread to read data and push that to the socket
        self._notify_recv, self._notify_send = socket.socketpair()
        self._notify_recv.setblocking(False)
        self._notify_send.setblocking(False)

        self._stop_lock = threading.Lock()
        self.stop = False

        self._event_queue: queue.Queue[QueueEvent] = queue.Queue()

        self._thread: threading.Thread | None = None

        super().__init__(
            descriptor=VisaDescriptor.from_string(descriptor),
            alias=alias,
            stop_conditions=stop_conditions,
            timeout=timeout,
            encoding=encoding,
            event_callback=event_callback,
            auto_open=auto_open,
        )

    def _default_timeout(self) -> Timeout:
        return Timeout(response=5, action="error")

    def _default_stop_conditions(self) -> list[StopCondition]:
        return [Continuation(0.1)]

    @classmethod
    def list_devices(cls: type["Visa"]) -> list[str]:
        """
        Returns a list of available VISA devices
        """
        if pyvisa is None:
            raise ImportError(
                "Missing optional dependency 'pyvisa'. Install with:\n"
                "  python -m pip install pyvisa"
            )

        rm = pyvisa.ResourceManager()
        available_resources: list[str] = []
        for device in rm.list_resources():
            try:
                d = rm.open_resource(device)
                d.close()
                available_resources.append(device)
            except pyvisa.VisaIOError:
                # Device cannot be opened; skip it
                pass

        return available_resources

    def _worker_close(self) -> None:
        # with self._inst_lock:
        # Stop the thread
        if self._thread is not None:
            with self._stop_lock:
                self.stop = True
                self._thread.join(timeout=self.THREAD_STOP_DELAY)

        # if self._inst is not None:
        #     self._inst.close()
        self._opened = False

    def _worker_write(self, data: bytes) -> None:
        # TODO : Add try around write
        # TODO : We assume that the instance is thread safe because
        # it would slow things down to have a lock because the internal thread
        # would release it every cycle (50ms)

        # with self._inst_lock:
        if self._inst is not None:
            self._inst.write_raw(data)

    def _worker_read(self, fragment_timestamp: float) -> Fragment:
        self._notify_recv.recv(1)
        event = self._event_queue.get(block=False, timeout=None)

        if isinstance(event, DisconnectedEvent):
            # Signal that the adapter disconnected
            return Fragment(b"", fragment_timestamp)
        if isinstance(event, FragmentEvent):
            return event.fragment

        raise AdapterReadError("Invalid queue event")

    def _worker_open(self) -> None:
        self._worker_check_descriptor()

        if self._thread is not None:
            self.close()

        # if self._inst is None:
        # NOTE: self._rm is always defined in __init__ when pyvisa is present

        self._inst = cast(
            MessageBasedResource,
            self._rm.open_resource(self._worker_descriptor.descriptor),
        )
        self._inst.write_termination = ""
        self._inst.read_termination = None

        self._opened = True

        self._thread = threading.Thread(
            target=self._internal_thread,
            args=(self._inst,),
            daemon=True,
        )
        self._thread.start()

    def _internal_thread(self, instance: MessageBasedResource) -> None:
        timeout = 50e-3
        while True:
            payload = b""
            fragment: Fragment | None = None
            try:
                instance.timeout = timeout
            except pyvisa.InvalidSession:
                return
            try:
                while True:
                    # Read up to an error
                    payload += instance.read_bytes(1)  # TODO : Maybe test with read_raw
                    instance.timeout = 0
            except pyvisa.VisaIOError:
                # Timeout
                if payload:
                    if fragment is None:
                        fragment = Fragment(payload, time.time())
                    else:
                        fragment.data += payload
                    # Tell the session that there's data (write to a virtual socket)
                    self._event_queue.put(FragmentEvent(fragment))
                    self._notify_send.send(b"1")
            except (TypeError, pyvisa.InvalidSession, BrokenPipeError):
                self._event_queue.put(DisconnectedEvent())
                self._notify_send.send(b"1")

            with self._stop_lock:
                if self.stop:
                    instance.close()
                    break

    def _selectable(self) -> HasFileno | None:
        return self._notify_recv
