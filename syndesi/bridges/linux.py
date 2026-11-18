# File : linux.py
# Author : Sébastien Deriaz
# License : GPL
"""
Native buses of Linux, as bridges : the kernel is the converter

LinuxI2C drives /dev/i2c-N and LinuxSPI drives /dev/spidevB.C, through the ioctls of the
i2c-dev and spidev drivers, without any dependency. They are bridges like any other :
an ioctl blocks for the whole transaction, so it runs on the bridge thread and never on
the reactor

I2C("/dev/i2c-1", ...) and SPI("/dev/spidev0.0", mode=..., speed_hz=...) build them and
configure them, there is no need to use them directly
"""

from __future__ import annotations

import ctypes
import glob
import os
import re
import sys
import threading
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from ..tools.errors import AdapterConfigurationError, AdapterOpenError, AdapterWriteError
from .bridge import I2CBridge, SPIBridge

# ┌─────────────┐
# │ ioctl codes │
# └─────────────┘

# linux/i2c-dev.h, linux/i2c.h
_I2C_RDWR = 0x0707
_I2C_M_RD = 0x0001

# linux/spi/spidev.h, _IOW(SPI_IOC_MAGIC, nr, type) = 0x40000000 | size << 16 | "k" << 8 | nr
_SPI_IOC_WR_MODE = 0x40016B01
_SPI_IOC_WR_BITS_PER_WORD = 0x40016B03
_SPI_IOC_WR_MAX_SPEED_HZ = 0x40046B04


def _spi_ioc_message(count: int) -> int:
    """SPI_IOC_MESSAGE(count)"""
    return 0x40006B00 | (ctypes.sizeof(_SpiIocTransfer) * count) << 16


class _I2CMsg(ctypes.Structure):
    _fields_ = [
        ("addr", ctypes.c_uint16),
        ("flags", ctypes.c_uint16),
        ("len", ctypes.c_uint16),
        ("buf", ctypes.POINTER(ctypes.c_uint8)),
    ]


class _I2CRdwrIoctlData(ctypes.Structure):
    _fields_ = [
        ("msgs", ctypes.POINTER(_I2CMsg)),
        ("nmsgs", ctypes.c_uint32),
    ]


class _SpiIocTransfer(ctypes.Structure):
    _fields_ = [
        ("tx_buf", ctypes.c_uint64),
        ("rx_buf", ctypes.c_uint64),
        ("len", ctypes.c_uint32),
        ("speed_hz", ctypes.c_uint32),
        ("delay_usecs", ctypes.c_uint16),
        ("bits_per_word", ctypes.c_uint8),
        ("cs_change", ctypes.c_uint8),
        ("tx_nbits", ctypes.c_uint8),
        ("rx_nbits", ctypes.c_uint8),
        ("word_delay_usecs", ctypes.c_uint8),
        ("pad", ctypes.c_uint8),
    ]


def _ioctl(fd: int, request: int, argument: Any) -> None:
    # Imported here : fcntl doesn't exist on Windows, where nothing of this is used
    import fcntl  # pylint: disable=import-outside-toplevel

    fcntl.ioctl(fd, request, argument)


def _open_device(path: str) -> int:
    try:
        return os.open(path, os.O_RDWR)
    except OSError as e:
        raise AdapterOpenError(f"Cannot open {path} : {e.strerror}") from e


# ┌─────┐
# │ I2C │
# └─────┘


class LinuxI2C(I2CBridge):
    """
    I2C bus of the machine, /dev/i2c-N (Raspberry Pi, SMBus of a motherboard, ...)

    The device file opens on the first transfer, it closes with close_bridge() or when
    the bridge is garbage collected. Needs the i2c-dev module and read/write access to
    the file (group i2c on most distributions)

    Parameters
    ----------
    path : str
        /dev/i2c-N
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self._fd: int | None = None
        self._close_fd: weakref.finalize[Any, LinuxI2C] | None = None

    def i2c_transfer(self, address: int, data: bytes, read_length: int) -> bytes:
        fd = self._open()
        write_buffer = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
        read_buffer = (ctypes.c_uint8 * read_length)()
        messages: list[_I2CMsg] = []
        # A transfer that reads nothing still writes, if only the address : b"" probes
        if data or not read_length:
            messages.append(_I2CMsg(address, 0, len(data), write_buffer))
        if read_length:
            messages.append(_I2CMsg(address, _I2C_M_RD, read_length, read_buffer))
        array = (_I2CMsg * len(messages))(*messages)
        try:
            _ioctl(fd, _I2C_RDWR, _I2CRdwrIoctlData(array, len(messages)))
        except OSError as e:
            raise AdapterWriteError(
                f"I2C transfer to {address:#04x} on {self.path} failed : {e.strerror}"
            ) from e
        return bytes(read_buffer)

    def close_bridge(self) -> None:
        self.run(self._close).result()
        super().close_bridge()

    def _open(self) -> int:
        if self._fd is None:
            self._fd = _open_device(self.path)
            self._close_fd = weakref.finalize(self, os.close, self._fd)
        return self._fd

    def _close(self) -> None:
        if self._close_fd is not None:
            self._close_fd()
        self._fd = None
        self._close_fd = None

    @property
    def bridge_name(self) -> str:
        """The device file, one bridge per file"""
        return self.path


# ┌─────┐
# │ SPI │
# └─────┘


@dataclass(frozen=True)
class SPISettings:
    """
    Mode, clock and word size of a chip select, None keeps what is configured

    Parameters
    ----------
    mode : int or None
        SPI mode 0 to 3
    speed_hz : int or None
        Clock frequency
    bits_per_word : int or None
        8 on most systems
    """

    mode: int | None = None
    speed_hz: int | None = None
    bits_per_word: int | None = None

    def __post_init__(self) -> None:
        if self.mode is not None and self.mode not in range(4):
            raise ValueError(f"Invalid SPI mode : {self.mode}, must be 0 to 3")
        for name in ("speed_hz", "bits_per_word"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"Invalid SPI {name} : {value}")

    def over(self, default: SPISettings) -> SPISettings:
        """These settings, completed by default where they are None"""
        return SPISettings(
            default.mode if self.mode is None else self.mode,
            default.speed_hz if self.speed_hz is None else self.speed_hz,
            default.bits_per_word if self.bits_per_word is None else self.bits_per_word,
        )

    def __bool__(self) -> bool:
        return self != SPISettings()


class LinuxSPI(SPIBridge):
    """
    SPI bus of the machine, /dev/spidevB.C where B is the bus and C the chip select

    One device file per chip select, each opens on its first transfer and they close
    with close_bridge() or when the bridge is garbage collected. Needs the spidev driver
    bound to the chip selects (device tree overlay on a Raspberry Pi)

    The kernel keeps a mode and a clock per chip select : the ones given here are the
    defaults of the bus, configure() sets those of one chip select. SPI("/dev/spidevB.C",
    mode=..., speed_hz=...) calls it

    Parameters
    ----------
    bus : int
        B in /dev/spidevB.C
    mode : int or None
        SPI mode 0 to 3, None keeps the one already configured
    speed_hz : int or None
        Clock frequency, None keeps the one already configured
    bits_per_word : int or None
        None keeps the one already configured, 8 on most systems
    """

    def __init__(
        self,
        bus: int,
        *,
        mode: int | None = None,
        speed_hz: int | None = None,
        bits_per_word: int | None = None,
    ) -> None:
        self.bus = bus
        self.defaults = SPISettings(mode, speed_hz, bits_per_word)
        self._settings: dict[int, SPISettings] = {}
        self._fds: dict[int, int] = {}
        # A dict, not a list : the finalizer must see the files opened after it
        weakref.finalize(self, _close_all, self._fds)

    def configure(self, cs: int, settings: SPISettings) -> None:
        """
        Set the mode, clock and word size of one chip select

        None keeps the default of the bus. Applied at once if the device file is open,
        otherwise when it opens. The last call wins for a chip select
        """
        self.run(self._configure, cs, settings).result()

    def settings(self, cs: int) -> SPISettings:
        """What applies to a chip select : its own settings, then the bus defaults"""
        return self._settings.get(cs, SPISettings()).over(self.defaults)

    def spi_transfer(self, cs: int, data: bytes) -> bytes:
        fd = self._open(cs)
        settings = self.settings(cs)
        tx = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
        rx = (ctypes.c_uint8 * len(data))()
        transfer = _SpiIocTransfer(
            tx_buf=ctypes.addressof(tx),
            rx_buf=ctypes.addressof(rx),
            len=len(data),
            speed_hz=settings.speed_hz or 0,
            bits_per_word=settings.bits_per_word or 0,
        )
        try:
            _ioctl(fd, _spi_ioc_message(1), transfer)
        except OSError as e:
            raise AdapterWriteError(
                f"SPI transfer on {self._path(cs)} failed : {e.strerror}"
            ) from e
        return bytes(rx)

    def close_bridge(self) -> None:
        self.run(_close_all, self._fds).result()
        super().close_bridge()

    def _configure(self, cs: int, settings: SPISettings) -> None:
        """Bridge thread, like the transfers that use the settings"""
        self._settings[cs] = settings
        fd = self._fds.get(cs)
        if fd is not None:
            try:
                self._apply(fd, cs)
            except OSError as e:
                raise AdapterConfigurationError(
                    f"Cannot configure {self._path(cs)} : {e.strerror}"
                ) from e

    def _apply(self, fd: int, cs: int) -> None:
        settings = self.settings(cs)
        if settings.mode is not None:
            _ioctl(fd, _SPI_IOC_WR_MODE, ctypes.c_uint8(settings.mode))
        if settings.bits_per_word is not None:
            _ioctl(fd, _SPI_IOC_WR_BITS_PER_WORD, ctypes.c_uint8(settings.bits_per_word))
        if settings.speed_hz is not None:
            _ioctl(fd, _SPI_IOC_WR_MAX_SPEED_HZ, ctypes.c_uint32(settings.speed_hz))

    def _open(self, cs: int) -> int:
        fd = self._fds.get(cs)
        if fd is not None:
            return fd
        path = self._path(cs)
        fd = _open_device(path)
        try:
            self._apply(fd, cs)
        except OSError as e:
            os.close(fd)
            raise AdapterOpenError(f"Cannot configure {path} : {e.strerror}") from e
        self._fds[cs] = fd
        return fd

    def _path(self, cs: int) -> str:
        return f"/dev/spidev{self.bus}.{cs}"

    @property
    def bridge_name(self) -> str:
        """The device file prefix, one bridge per bus"""
        return f"/dev/spidev{self.bus}"


def _close_all(fds: dict[int, int]) -> None:
    for fd in fds.values():
        os.close(fd)
    fds.clear()


# ┌──────────────────────┐
# │ Path to native bridge │
# └──────────────────────┘

_SPIDEV_PATTERN = re.compile(r"^/dev/spidev(\d+)\.(\d+)$")


def _numbers(path: str) -> list[int]:
    """Sort key : /dev/i2c-10 after /dev/i2c-9"""
    return [int(n) for n in re.findall(r"\d+", path)]


def list_i2c_buses() -> list[str]:
    """The I2C buses of the machine, /dev/i2c-N, empty outside of Linux"""
    return sorted(glob.glob("/dev/i2c-[0-9]*"), key=_numbers)


def list_spi_devices() -> list[str]:
    """The SPI chip selects of the machine, /dev/spidevB.C, empty outside of Linux"""
    return sorted(glob.glob("/dev/spidev[0-9]*.[0-9]*"), key=_numbers)


BridgeT = TypeVar("BridgeT", LinuxI2C, LinuxSPI)

# One bridge per bus : the I2C adapters of the same bus then share its thread and its
# file, like the ones built on a user bridge. Weak, so that a bus nobody uses anymore
# closes its file
_bridges: weakref.WeakValueDictionary[Any, Any] = weakref.WeakValueDictionary()
_bridges_lock = threading.Lock()


def _shared(key: Any, factory: Callable[[], BridgeT]) -> BridgeT:
    if not sys.platform.startswith("linux"):
        raise AdapterConfigurationError(
            f"No native I2C/SPI on {sys.platform}, give a bridge instead of a path"
        )
    with _bridges_lock:
        bridge: BridgeT | None = _bridges.get(key)
        if bridge is None:
            bridge = factory()
            _bridges[key] = bridge
        return bridge


def linux_i2c(path: str) -> LinuxI2C:
    """The LinuxI2C of path, created on first use and shared afterwards"""
    return _shared(("i2c", path), lambda: LinuxI2C(path))


def linux_spi(path: str) -> tuple[LinuxSPI, int]:
    """The LinuxSPI and the chip select of /dev/spidevB.C, the bridge is shared"""
    match = _SPIDEV_PATTERN.match(path)
    if match is None:
        raise AdapterConfigurationError(
            f"Invalid SPI device : {path!r}, expected /dev/spidevB.C"
        )
    bus, cs = int(match.group(1)), int(match.group(2))
    return _shared(("spi", bus), lambda: LinuxSPI(bus)), cs
