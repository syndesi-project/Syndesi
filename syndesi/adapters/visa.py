# File : visa.py
# Author : Sébastien Deriaz
# License : GPL
"""
VISA adapter, uses a VISA backend like pyvisa-py or NI to talk to instruments

pyvisa is blocking and exposes no file descriptor, so this backend reads in a thread and
makes itself selectable through a socketpair, see reader_thread
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from types import EllipsisType
from typing import TYPE_CHECKING, cast

from ..tools.errors import (
    AdapterDisconnectedError,
    AdapterOpenError,
    AdapterWriteError,
)
from .adapter import Adapter, AsyncAdapter
from .engine import AdapterBackend, Descriptor
from .framer import BytesFramer
from .reader_thread import ThreadedReader
from .stop_conditions import Continuation, StopCondition
from .utils import Fragment, HasFileno, TimeoutParameterType, TimeoutType

try:
    import pyvisa
except ImportError:  # pragma: no cover - optional dependency
    pyvisa = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from pyvisa.resources import MessageBasedResource

_MISSING_PYVISA = (
    "Missing optional dependency 'pyvisa'. Install with:\n  python -m pip install pyvisa"
)

def _require_pyvisa() -> None:
    if pyvisa is None:
        raise ImportError(_MISSING_PYVISA)

@dataclass
class VisaDescriptor(Descriptor):
    """
    VISA descriptor

    Examples
    --------
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
        r"^([A-Z]+)(\d*|\/[^:]+)?::([^:]+)(?:::([^:]+))?"
        + "(?:::([^:]+))?(?:::([^:]+))?::(INSTR|SOCKET)$"
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
        if re.match(VisaDescriptor.DETECTION_PATTERN, string):
            return VisaDescriptor(descriptor=string)
        raise ValueError(f"Could not parse descriptor : {string}")

    def __str__(self) -> str:
        return str(self.descriptor)

    def is_initialized(self) -> bool:
        return True


def default_stop_conditions() -> list[StopCondition]:
    """
    Stop-conditions of a new VISA adapter

    A function, not a module level list : a stop-condition holds the state of the frame
    being assembled, so two adapters must never share the same instances
    """
    return [Continuation(continuation=0.1)]


def list_devices() -> list[str]:
    """
    Return the VISA devices that can actually be opened
    """
    _require_pyvisa()
    rm = pyvisa.ResourceManager()
    available: list[str] = []
    for device in rm.list_resources():
        try:
            handle = rm.open_resource(device)
            handle.close()
            available.append(device)
        except pyvisa.VisaIOError:
            pass  # the device exists but cannot be opened, skip it
    return available


class VisaBackend(AdapterBackend[VisaDescriptor, bytes]):
    """
    Talks to a VISA instrument through pyvisa

    pyvisa gives neither a file descriptor nor a non-blocking read, so a ThreadedReader
    polls the instrument and wakes the reactor through a socketpair. That thread is what
    makes the timestamps usable : it stamps a fragment as soon as the bytes stop coming

    Parameters
    ----------
    descriptor : VisaDescriptor
    """

    # How long a poll waits for the first byte of a fragment, in milliseconds
    POLL_TIMEOUT_MS = 50

    def __init__(self, descriptor: VisaDescriptor) -> None:
        super().__init__(descriptor)
        _require_pyvisa()
        self._rm = pyvisa.ResourceManager()
        self._instrument: MessageBasedResource | None = None
        self._reader: ThreadedReader[bytes] | None = None

    def selectable(self) -> HasFileno | None:
        if self._reader is None:
            return None
        return self._reader.selectable()

    def open(self, timeout: float | None) -> None:
        del timeout  # pyvisa carries its own, and the reader polls
        try:
            instrument = cast(
                "MessageBasedResource",
                self._rm.open_resource(self.descriptor.descriptor),
            )
        except pyvisa.VisaIOError as e:
            raise AdapterOpenError(
                f"Failed to open adapter {self.descriptor} ({e})"
            ) from None

        # Syndesi does the framing, pyvisa must not cut anything itself
        instrument.write_termination = ""
        instrument.read_termination = None

        self._instrument = instrument
        self._reader = ThreadedReader(
            self._read_blocking, name=f"syndesi-visa-{self.descriptor}"
        )
        self._reader.start()

    def close(self) -> None:
        # The reader first : it must stop touching the instrument before it is closed
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
        if self._instrument is not None:
            try:
                self._instrument.close()
            except pyvisa.Error:
                pass
            self._instrument = None

    def read(self, fragment_timestamp: float) -> Fragment[bytes]:
        if self._reader is None:
            raise AdapterDisconnectedError()
        return self._reader.read(fragment_timestamp)

    def write(self, data: bytes) -> None:
        if self._instrument is None:
            raise AdapterWriteError(f"{self.descriptor} is not open")
        try:
            self._instrument.write_raw(data)
        except pyvisa.Error as e:
            raise AdapterWriteError(
                f"Cannot write to {self.descriptor} ({e})"
            ) from e

    @property
    def default_timeout(self) -> TimeoutType:
        return 5.0

    def _read_blocking(self) -> bytes | None:
        """
        One poll for the ThreadedReader

        Waits POLL_TIMEOUT_MS for a first byte, then drains whatever follows without
        waiting. The whole burst becomes one fragment, which is what the
        stop-conditions expect
        """
        instrument = self._instrument
        if instrument is None:
            return None

        payload = b""
        try:
            instrument.timeout = self.POLL_TIMEOUT_MS
            payload += instrument.read_bytes(1)
            instrument.timeout = 0
            while True:
                payload += instrument.read_bytes(1)
        except pyvisa.VisaIOError:
            pass  # nothing more for now, the fragment ends here
        except (TypeError, pyvisa.InvalidSession, BrokenPipeError) as e:
            raise AdapterDisconnectedError() from e

        return payload or None


class Visa(Adapter[VisaDescriptor, bytes]):
    """
    VISA adapter, reads and writes bytes

    Parameters
    ----------
    descriptor : str
        VISA resource name, see VisaDescriptor for the forms it takes
    timeout : float, None or ...
        Time to wait for the instrument to respond, 5 s by default
    stop_conditions : StopCondition, list of StopCondition or ...
        When a frame is complete, Continuation(0.1) by default
    alias : str
    auto_open : bool
    """

    def __init__(
        self,
        descriptor: str,
        *,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        super().__init__(
            VisaBackend(VisaDescriptor.from_string(descriptor)),
            BytesFramer(default_stop_conditions()),
            timeout,
            stop_conditions=stop_conditions,
            alias=alias,
            auto_open=auto_open,
        )

    @staticmethod
    def list_devices() -> list[str]:
        """Return the VISA devices that can actually be opened"""
        return list_devices()


class AsyncVisa(AsyncAdapter[VisaDescriptor, bytes]):
    """
    Async VISA adapter, same parameters as Visa
    """

    def __init__(
        self,
        descriptor: str,
        *,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | list[StopCondition] | EllipsisType = ...,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        super().__init__(
            VisaBackend(VisaDescriptor.from_string(descriptor)),
            BytesFramer(default_stop_conditions()),
            timeout,
            stop_conditions=stop_conditions,
            alias=alias,
            auto_open=auto_open,
        )

    @staticmethod
    def list_devices() -> list[str]:
        """Return the VISA devices that can actually be opened"""
        return list_devices()
