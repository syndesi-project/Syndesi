# File : hid.py
# Author : Sébastien Deriaz
# License : GPL
"""
HID adapter, the raw reports of a HID device (USB, Bluetooth, ...), through hidapi

HID is an adapter and not a protocol on top of USB : on Windows and macOS the operating
system owns the HID interfaces, so they can't be reached through raw USB, and HID also
exists over Bluetooth and I2C

One report is one fragment. FragmentSC is the default stop-condition, so that every
report received is a frame of its own : HID converters answer each command with one
report, and a Continuation would glue together the reports arriving in a burst

    dev = HID(0x04D8, 0x00DD)               # vendor id, product id
    dev.query(b"\\x10")                      # one report out, the report that answers it

Report ids :

- writes : hidapi expects the report id as the first byte. With report_id=0 (default,
  devices without numbered reports) the adapter adds it, report_id=N adds N, and
  report_id=None sends the data as is (the caller writes the id)
- reads : a numbered report starts with its id, an unnumbered one has none, as hidapi
  returns them

hidapi exposes no file descriptor, the reads run in a ThreadedReader (like Visa). Writes
and feature reports run on the reactor : a HID write is a short blocking call, and
reading and writing from two threads is how hidapi is meant to be used
"""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Any

from ..tools.errors import (
    AdapterConfigurationError,
    AdapterDisconnectedError,
    AdapterOpenError,
    AdapterReadError,
    AdapterWriteError,
)
from ..tools.others import DEFAULT, DefaultType
from .adapter import Adapter, AsyncAdapter
from .engine import AdapterBackend, Descriptor
from .framer import BytesFramer
from .reader_thread import ThreadedReader
from .stop_conditions import FragmentSC, StopCondition
from .utils import Fragment, HasFileno, TimeoutParameterType, TimeoutType

try:
    import hid as _hidapi  # type: ignore[import-not-found, unused-ignore]
except ImportError:  # pragma: no cover - optional dependency
    _hidapi = None

_MISSING_HIDAPI = """Missing optional dependency 'hidapi'. Install with:
  python -m pip install "syndesi[hid]\""""


def _require_hidapi() -> Any:
    if _hidapi is None:
        raise ImportError(_MISSING_HIDAPI)
    return _hidapi


# ┌────────────┐
# │ Descriptor │
# └────────────┘

_ID_PATTERN = re.compile(
    r"^(?P<vid>[0-9a-fA-F]{4}):(?P<pid>[0-9a-fA-F]{4})"
    r"(?::(?P<serial>[^@]+))?(?:@(?P<interface>\d+))?$"
)
_PATH_PREFIX = "path="


@dataclass
class HIDDescriptor(Descriptor):
    """
    Which HID device to open

    Written hid:VID:PID, with the ids in hexadecimal, followed by :SERIAL and @INTERFACE
    when they are given : hid:04d8:00dd, hid:04d8:00dd:0001234567@2. A device opened by
    its path is written hid:path=..., the path being the one list_devices() gives
    """

    SCHEMES = ("hid",)
    vendor_id: int | None = None
    product_id: int | None = None
    serial_number: str | None = None
    interface: int | None = None
    path: str | None = None

    @staticmethod
    def from_string(string: str) -> HIDDescriptor:
        _, target = HIDDescriptor.split_scheme(string)
        if target.startswith(_PATH_PREFIX):
            path = target[len(_PATH_PREFIX) :]
            if not path:
                raise ValueError(f"Invalid descriptor : {string!r}, the path is empty")
            return HIDDescriptor(path=path)
        match = _ID_PATTERN.match(target)
        if match is None:
            raise ValueError(
                f"Invalid descriptor : {string!r}, expected hid:VID:PID[:SERIAL][@INTERFACE]"
                " or hid:path=PATH"
            )
        interface = match.group("interface")
        return HIDDescriptor(
            vendor_id=int(match.group("vid"), 16),
            product_id=int(match.group("pid"), 16),
            serial_number=match.group("serial"),
            interface=None if interface is None else int(interface),
        )

    def is_initialized(self) -> bool:
        return self.path is not None or (
            self.vendor_id is not None and self.product_id is not None
        )

    def __str__(self) -> str:
        if self.vendor_id is None or self.product_id is None:
            return f"hid:{_PATH_PREFIX}{self.path}"
        output = f"hid:{self.vendor_id:04x}:{self.product_id:04x}"
        if self.serial_number:
            output += f":{self.serial_number}"
        if self.interface is not None:
            output += f"@{self.interface}"
        return output


# ┌─────────────┐
# │ Enumeration │
# └─────────────┘


@dataclass(frozen=True)
class HIDDeviceInfo:  # pylint: disable=too-many-instance-attributes
    """
    A HID device found by list_devices()

    Attributes
    ----------
    path : str
        Platform specific path, pass it as HID(path=...) to open this very interface
    vendor_id, product_id : int
    serial_number, manufacturer, product : str
        Empty when the device doesn't give them
    interface : int
        USB interface number, -1 if unknown (Bluetooth, ...)
    usage_page, usage : int
        What the interface is for (0xFF00 and above : vendor defined)
    release : int
        Device release number, BCD
    """

    path: str
    vendor_id: int
    product_id: int
    serial_number: str
    manufacturer: str
    product: str
    interface: int
    usage_page: int
    usage: int
    release: int

    @property
    def descriptor(self) -> str:
        """Descriptor string of this device, see HIDDescriptor"""
        return str(
            HIDDescriptor(
                self.vendor_id,
                self.product_id,
                self.serial_number or None,
                self.interface if self.interface >= 0 else None,
            )
        )

    def __str__(self) -> str:
        name = " ".join(part for part in (self.manufacturer, self.product) if part)
        return f"{self.descriptor}  {name}".rstrip()


def _path_text(path: bytes | str) -> str:
    return os.fsdecode(path) if isinstance(path, bytes) else path


def list_devices(
    vendor_id: int | None = None, product_id: int | None = None
) -> list[HIDDeviceInfo]:
    """
    Return the HID interfaces connected, optionally only those of a vendor or a product

    A device with several HID interfaces appears once per interface
    """
    hidapi = _require_hidapi()
    devices: list[HIDDeviceInfo] = []
    # pylint: disable-next=c-extension-no-member
    for entry in hidapi.enumerate(vendor_id or 0, product_id or 0):
        devices.append(
            HIDDeviceInfo(
                path=_path_text(entry.get("path", b"")),
                vendor_id=int(entry.get("vendor_id", 0)),
                product_id=int(entry.get("product_id", 0)),
                serial_number=entry.get("serial_number") or "",
                manufacturer=entry.get("manufacturer_string") or "",
                product=entry.get("product_string") or "",
                interface=int(entry.get("interface_number", -1)),
                usage_page=int(entry.get("usage_page", 0)),
                usage=int(entry.get("usage", 0)),
                release=int(entry.get("release_number", 0)),
            )
        )
    return devices


def _find_path(descriptor: HIDDescriptor) -> bytes:
    """Path of the first interface matching the descriptor"""
    if descriptor.path is not None:
        return os.fsencode(descriptor.path)
    for device in list_devices(descriptor.vendor_id, descriptor.product_id):
        if descriptor.serial_number and device.serial_number != descriptor.serial_number:
            continue
        if descriptor.interface is not None and device.interface != descriptor.interface:
            continue
        return os.fsencode(device.path)
    raise AdapterOpenError(f"Failed to open adapter {descriptor} (no such HID device)")


# ┌─────────┐
# │ Backend │
# └─────────┘


def default_stop_conditions() -> list[StopCondition]:
    """
    Stop-conditions of a new HID adapter : every report is a frame

    A function, not a module level list : a stop-condition holds the state of the frame
    being assembled, so two adapters must never share the same instances
    """
    return [FragmentSC()]


class HIDBackend(AdapterBackend[HIDDescriptor, bytes]):
    """
    Talks to a HID device through hidapi

    Parameters
    ----------
    descriptor : HIDDescriptor
    report_id : int or None
        Added in front of every write, None to send the data as is
    report_size : int or None
        Size of an output report : shorter writes are padded with zeros, longer ones are
        refused. None sends the data as it is. Windows needs every report at its full
        size
    """

    # How long a read waits for a report before checking whether to stop, milliseconds
    POLL_TIMEOUT_MS = 50
    # Largest input report read, high speed devices go up to 1024 bytes
    READ_SIZE = 1024

    def __init__(
        self,
        descriptor: HIDDescriptor,
        report_id: int | None = 0,
        report_size: int | None = None,
    ) -> None:
        super().__init__(descriptor)
        self._hidapi = _require_hidapi()
        if report_id is not None and not 0 <= report_id <= 0xFF:
            raise AdapterConfigurationError(f"Invalid report id : {report_id}")
        if report_size is not None and report_size <= 0:
            raise AdapterConfigurationError(f"Invalid report size : {report_size}")
        self.report_id = report_id
        self.report_size = report_size
        self._device: Any = None
        self._reader: ThreadedReader[bytes] | None = None

    def selectable(self) -> HasFileno | None:
        if self._reader is None:
            return None
        return self._reader.selectable()

    def open(self, timeout: float | None) -> None:
        del timeout  # hidapi opens without waiting
        path = _find_path(self.descriptor)
        device = self._hidapi.device()  # pylint: disable=c-extension-no-member
        try:
            device.open_path(path)
        except (OSError, ValueError) as e:
            raise AdapterOpenError(
                f"Failed to open adapter {self.descriptor} ({e or 'access denied?'})"
            ) from None
        self._device = device
        self._reader = ThreadedReader(
            self._read_once, name=f"syndesi-hid-{self.descriptor}"
        )
        self._reader.start()

    def close(self) -> None:
        # The reader first : it must stop touching the device before it is closed
        if self._reader is not None:
            self._reader.stop()
            self._reader = None
        if self._device is not None:
            try:
                self._device.close()
            except (OSError, ValueError):
                pass
            self._device = None

    def read(self, fragment_timestamp: float) -> Fragment[bytes]:
        if self._reader is None:
            raise AdapterDisconnectedError()
        return self._reader.read(fragment_timestamp)

    def write(self, data: bytes) -> None:
        report = self.output_report(data)
        device = self._open_device(AdapterWriteError)
        try:
            written = device.write(report)
        except (OSError, ValueError) as e:
            raise AdapterWriteError(f"Cannot write to {self.descriptor} ({e})") from e
        if written < 0:
            raise AdapterWriteError(f"Cannot write to {self.descriptor} ({self._error()})")

    @property
    def default_timeout(self) -> TimeoutType:
        return 1.0

    def output_report(self, data: bytes) -> bytes:
        """The bytes handed to hidapi for data : report id and padding added"""
        payload = bytes(data)
        if self.report_size is not None:
            if len(payload) > self.report_size:
                raise AdapterWriteError(
                    f"{self.descriptor} : {len(payload)} bytes don't fit in a "
                    f"{self.report_size} bytes report"
                )
            payload = payload.ljust(self.report_size, b"\x00")
        if self.report_id is not None:
            payload = bytes([self.report_id]) + payload
        return payload

    # Feature reports, run on the reactor through AdapterEngine.call

    def send_feature_report(self, data: bytes, report_id: int) -> None:
        """Send a feature report, report_id followed by data"""
        device = self._open_device(AdapterWriteError)
        try:
            written = device.send_feature_report(bytes([report_id]) + bytes(data))
        except (OSError, ValueError) as e:
            raise AdapterWriteError(
                f"Cannot send a feature report to {self.descriptor} ({e})"
            ) from e
        if written < 0:
            raise AdapterWriteError(
                f"Cannot send a feature report to {self.descriptor} ({self._error()})"
            )

    def get_feature_report(self, report_id: int, length: int) -> bytes:
        """Read feature report report_id, length bytes at most, without its id"""
        device = self._open_device(AdapterReadError)
        try:
            # hidapi reads the report id too, in the first byte
            report = bytes(device.get_feature_report(report_id, length + 1))
        except (OSError, ValueError) as e:
            raise AdapterReadError(
                f"Cannot get feature report {report_id} from {self.descriptor} ({e})"
            ) from e
        return report[1:]

    # Internals

    def _open_device(self, error: type[Exception]) -> Any:
        if self._device is None:
            raise error(f"{self.descriptor} is not open")
        return self._device

    def _error(self) -> str:
        try:
            return str(self._device.error()) or "unknown error"
        except Exception:  # pylint: disable=broad-exception-caught
            return "unknown error"

    def _read_once(self) -> bytes | None:
        """One read for the ThreadedReader : one report, or None after the poll timeout"""
        device = self._device
        if device is None:
            return None
        try:
            report = device.read(self.READ_SIZE, self.POLL_TIMEOUT_MS)
        except (OSError, ValueError) as e:
            # hidapi fails reads once the device is unplugged
            raise AdapterDisconnectedError(f"{self.descriptor} : {e}") from e
        return bytes(report) or None


# ┌──────────┐
# │ Adapters │
# └──────────┘


def _descriptor(
    vendor_id: int | None,
    product_id: int | None,
    serial_number: str | None,
    interface: int | None,
    path: str | None,
) -> HIDDescriptor:
    if path is None and (vendor_id is None or product_id is None):
        raise AdapterConfigurationError(
            "A HID device is given by its vendor and product ids, or by its path"
        )
    return HIDDescriptor(vendor_id, product_id, serial_number, interface, path)


class HID(Adapter[HIDDescriptor, bytes]):
    """
    HID adapter, writes output reports and reads input reports

    Needs the hidapi package : pip install "syndesi[hid]"

    Parameters
    ----------
    vendor_id : int or None
        USB vendor id, 0x04D8 for Microchip
    product_id : int or None
        USB product id
    serial_number : str or None
        To choose between several identical devices
    interface : int or None
        USB interface number, for a device with several HID interfaces
    path : str or None
        Platform specific path, from list_devices(), instead of the ids
    report_id : int or None
        Added in front of every write, 0 by default (devices without numbered reports).
        None sends the data as is, the first byte being the report id
    report_size : int or None
        Size of an output report, without the id. Shorter writes are padded with zeros.
        None (default) sends the data at its own length. Windows needs full reports
    timeout : float, None or DEFAULT
        Time to wait for the device to respond, 1 s by default
    stop_conditions : StopCondition, list of StopCondition or DEFAULT
        FragmentSC() by default : one report, one frame
    alias : str
    auto_open : bool
        See Adapter
    """

    def __init__(
        self,
        vendor_id: int | None = None,
        product_id: int | None = None,
        *,
        serial_number: str | None = None,
        interface: int | None = None,
        path: str | None = None,
        report_id: int | None = 0,
        report_size: int | None = None,
        timeout: TimeoutParameterType = DEFAULT,
        stop_conditions: StopCondition | list[StopCondition] | DefaultType = DEFAULT,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        self._backend = HIDBackend(
            _descriptor(vendor_id, product_id, serial_number, interface, path),
            report_id,
            report_size,
        )
        super().__init__(
            self._backend,
            BytesFramer(default_stop_conditions()),
            timeout,
            stop_conditions=stop_conditions,
            alias=alias,
            auto_open=auto_open,
        )

    @staticmethod
    def list_devices(
        vendor_id: int | None = None, product_id: int | None = None
    ) -> list[HIDDeviceInfo]:
        """The HID interfaces connected, see list_devices"""
        return list_devices(vendor_id, product_id)

    def send_feature_report(self, data: bytes, report_id: int = 0) -> None:
        """
        Send a feature report

        Parameters
        ----------
        data : bytes
            Content of the report, without its id
        report_id : int
            0 for a device without numbered reports
        """
        self._engine.call(self._backend.send_feature_report, data, report_id).result()

    def get_feature_report(self, report_id: int, length: int) -> bytes:
        """
        Read a feature report

        Parameters
        ----------
        report_id : int
            0 for a device without numbered reports
        length : int
            Size of the report, without its id

        Returns
        -------
        bytes
            Content of the report, without its id
        """
        return self._engine.call(
            self._backend.get_feature_report, report_id, length
        ).result()


class AsyncHID(AsyncAdapter[HIDDescriptor, bytes]):
    """Async HID adapter, same parameters as HID"""

    def __init__(
        self,
        vendor_id: int | None = None,
        product_id: int | None = None,
        *,
        serial_number: str | None = None,
        interface: int | None = None,
        path: str | None = None,
        report_id: int | None = 0,
        report_size: int | None = None,
        timeout: TimeoutParameterType = DEFAULT,
        stop_conditions: StopCondition | list[StopCondition] | DefaultType = DEFAULT,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        self._backend = HIDBackend(
            _descriptor(vendor_id, product_id, serial_number, interface, path),
            report_id,
            report_size,
        )
        super().__init__(
            self._backend,
            BytesFramer(default_stop_conditions()),
            timeout,
            stop_conditions=stop_conditions,
            alias=alias,
            auto_open=auto_open,
        )

    @staticmethod
    def list_devices(
        vendor_id: int | None = None, product_id: int | None = None
    ) -> list[HIDDeviceInfo]:
        """The HID interfaces connected, see list_devices"""
        return list_devices(vendor_id, product_id)

    async def send_feature_report(self, data: bytes, report_id: int = 0) -> None:
        """See HID.send_feature_report"""
        await asyncio.wrap_future(
            self._engine.call(self._backend.send_feature_report, data, report_id)
        )

    async def get_feature_report(self, report_id: int, length: int) -> bytes:
        """See HID.get_feature_report"""
        return await asyncio.wrap_future(
            self._engine.call(self._backend.get_feature_report, report_id, length)
        )
