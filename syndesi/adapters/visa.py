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

from syndesi.adapters.adapter_worker import (
    AdapterDisconnectedEvent,
    AdapterEvent,
    HasFileno,
)
from syndesi.adapters.stop_conditions import Continuation, Fragment, StopCondition
from syndesi.component import Descriptor
from syndesi.tools.errors import AdapterReadError

from .adapter import Adapter
from .timeout import Timeout

# --- Runtime optional import
try:
    import pyvisa  # type: ignore
    from pyvisa.resources import Resource  # type: ignore
except ImportError:
    pyvisa = None
    Resource = None


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

    def __init__(
        self,
        descriptor: str,
        *,
        alias: str = "",
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        timeout: None | float | Timeout | EllipsisType = ...,
        encoding: str = "utf-8",
        event_callback: Callable[[AdapterEvent], None] | None = None,
    ) -> None:
        super().__init__(
            descriptor=VisaDescriptor.from_string(descriptor),
            alias=alias,
            stop_conditions=stop_conditions,
            timeout=timeout,
            encoding=encoding,
            event_callback=event_callback,
        )

        self._worker_descriptor: VisaDescriptor
        self._descriptor: VisaDescriptor

        self._logger.info("Setting up VISA IP adapter")

        if pyvisa is None:
            raise ImportError(
                "Missing optional dependency 'pyvisa'. Install with:\n"
                "  python -m pip install pyvisa"
            )

        self._rm = pyvisa.ResourceManager()
        self._inst: Resource | None = None  # annotation only; no runtime import needed

        # We need a socket pair because VISA doesn't expose a selectable fileno/socket
        # So we create a thread to read data and push that to the socket
        self._notify_recv, self._notify_send = socket.socketpair()
        self._notify_recv.setblocking(False)
        self._notify_send.setblocking(False)

        self._stop_lock = threading.Lock()
        self.stop = False

        self._fragment_lock = threading.Lock()
        self._fragment: Fragment | None = None
        self._event_queue: queue.Queue[AdapterEvent] = queue.Queue()

        self._thread = threading.Thread(
            target=self._internal_thread,
            args=(self._inst, self._event_queue),
            daemon=True,
        )
        self._thread.start()

        self._inst_lock = threading.Lock()

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
        with self._inst_lock:
            if self._inst is not None:
                self._inst.close()
            self._opened = False
            with self._stop_lock:
                self.stop = True

    def _worker_write(self, data: bytes) -> None:
        # TODO : Add try around write
        with self._inst_lock:
            if self._inst is not None:
                self._inst.write_raw(data)

    def _worker_read(self, fragment_timestamp: float) -> Fragment:
        self._notify_recv.recv(1)
        if not self._event_queue.empty():
            event = self._event_queue.get()
            if isinstance(event, AdapterDisconnectedEvent):
                # return Fragment(b"", fragment_timestamp)
                raise AdapterReadError("Could not read from adapter")

        with self._fragment_lock:
            if self._fragment is None:
                raise AdapterReadError("Invalid fragment")
            output = self._fragment
            self._fragment = None
            return output

    def _worker_open(self) -> None:
        self._worker_check_descriptor()

        if self._inst is None:
            # NOTE: self._rm is always defined in __init__ when pyvisa is present
            self._inst = self._rm.open_resource(self._worker_descriptor.descriptor)

        if not self._opened:
            # These attributes exist on pyvisa resources
            self._inst.write_termination = ""
            self._inst.read_termination = None
            self._opened = True

        # TODO : Tell the thread to open

    def _internal_thread(
        self,
        inst: Resource,
        event_queue: queue.Queue[AdapterEvent],
    ) -> None:
        timeout = 2000
        while True:
            payload = b""
            with self._fragment_lock:
                self._fragment = None  # Fragment(b"", None)
            try:
                inst.timeout = timeout
            except pyvisa.InvalidSession:
                pass
            try:
                while True:
                    # Read up to an error
                    payload += inst.read_bytes(1)
                    inst.timeout = 0
            except pyvisa.VisaIOError:
                # Timeout
                if payload:
                    with self._fragment_lock:
                        if self._fragment is None:
                            self._fragment = Fragment(payload, time.time())
                        else:
                            self._fragment.data += payload
                    # Tell the session that there's data (write to a virtual socket)
                    self._notify_send.send(b"1")
            except (TypeError, pyvisa.InvalidSession, BrokenPipeError):
                event_queue.put(AdapterDisconnectedEvent())
                self._notify_send.send(b"1")
            with self._stop_lock:
                if self.stop:
                    break

    def _selectable(self) -> HasFileno | None:
        return self._notify_recv
