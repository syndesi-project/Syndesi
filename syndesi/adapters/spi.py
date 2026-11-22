# File : spi.py
# Author : Sébastien Deriaz
# License : GPL
"""
SPI adapter, one device on an SPI bus

The bus is the machine's own (SPI("/dev/spidev0.0", mode=3), Linux only) or provided by
a bridge (SPI(MyBoard(...), cs=1)). Both work the same way, see BusBackend

SPI is full duplex : each write is a transaction, and the bytes received while it was
sent come back as a frame, as many as were written. query() and transfer() return them
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..bridges.bridge import SPIBridge
from ..bridges.linux import LinuxSPI, SPISettings, linux_spi, list_spi_devices
from ..errors import AdapterReadError
from ..tools.others import DEFAULT
from .adapter import Adapter, AsyncAdapter
from .bus import BusBackend
from .engine import Descriptor
from .framer import TrivialFramer
from .utils import TimeoutParameterType


@dataclass
class SPIDescriptor(Descriptor):
    """
    Bus and chip select of an SPI device, written spi:bus.cs : spi:/dev/spidev0.1

    bus is the device file prefix of a native bus, or the name of the bridge
    (spi:MyBoard.1)
    """

    SCHEMES = ("spi",)
    bus: str
    cs: int

    @staticmethod
    def from_string(string: str) -> SPIDescriptor:
        _, target = SPIDescriptor.split_scheme(string)
        match = re.match(r"^(.+)\.(\d+)$", target)
        if match is None:
            raise ValueError(f"Invalid descriptor : {string!r}, expected spi:bus.cs")
        return SPIDescriptor(match.group(1), int(match.group(2)))

    def is_initialized(self) -> bool:
        return True

    def __str__(self) -> str:
        return f"spi:{self.bus}.{self.cs}"


class SPIBackend(BusBackend[SPIDescriptor]):
    """
    Runs the SPI transactions of one device on its bridge

    Parameters
    ----------
    bridge : SPIBridge
    descriptor : SPIDescriptor
    """

    def __init__(self, bridge: SPIBridge, descriptor: SPIDescriptor) -> None:
        super().__init__(bridge, descriptor)
        self._spi_bridge = bridge

    def transfer(self, data: bytes) -> bytes:
        received = self._spi_bridge.spi_transfer(self.descriptor.cs, bytes(data))
        if len(received) != len(data):
            raise AdapterReadError(
                f"{self.descriptor} : expected {len(data)} bytes, "
                f"the bridge returned {len(received)}"
            )
        return received


def _backend(bus: str | SPIBridge, cs: int | None, settings: SPISettings) -> SPIBackend:
    if isinstance(bus, SPIBridge):
        bridge, bus_cs = bus, 0 if cs is None else cs
    else:
        bridge, bus_cs = linux_spi(bus)
        if cs is not None and cs != bus_cs:
            raise ValueError(f"{bus} is chip select {bus_cs}, not {cs}")
    if settings:
        if not isinstance(bridge, LinuxSPI):
            raise ValueError(
                f"{bridge} : mode, speed_hz and bits_per_word are settings of the "
                "bridge, configured by its driver"
            )
        # Only when given : an adapter without settings keeps those of the chip select
        bridge.configure(bus_cs, settings)
    return SPIBackend(bridge, SPIDescriptor(str(bridge), bus_cs))


class SPI(Adapter[SPIDescriptor, bytes]):
    """
    One device on an SPI bus

    Several SPI adapters can share a bus, one per chip select. Their transactions are
    run one at a time by the bridge

    Parameters
    ----------
    bus : str or SPIBridge
        /dev/spidevB.C for a native bus (Linux), or the bridge that provides the bus
    cs : int or None
        Chip select, 0 by default. Already in the path of a native bus
    mode : int or None
        SPI mode 0 to 3
    speed_hz : int or None
        Clock frequency
    bits_per_word : int or None
        8 on most systems
        These three are set for this chip select only, None keeps what is configured.
        Native bus only : a bridge configures its bus in its driver
    timeout : float, None or DEFAULT
    alias : str
    auto_open : bool
        See Adapter
    """

    def __init__(
        self,
        bus: str | SPIBridge,
        cs: int | None = None,
        *,
        mode: int | None = None,
        speed_hz: int | None = None,
        bits_per_word: int | None = None,
        timeout: TimeoutParameterType = DEFAULT,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        super().__init__(
            _backend(bus, cs, SPISettings(mode, speed_hz, bits_per_word)),
            TrivialFramer(),
            timeout,
            alias=alias,
            auto_open=auto_open,
        )

    @staticmethod
    def list_buses() -> list[str]:
        """The native SPI chip selects, /dev/spidevB.C (Linux)"""
        return list_spi_devices()

    def transfer(self, data: bytes) -> bytes:
        """Send data and return the bytes received meanwhile, same as query()"""
        return self.query(data)


class AsyncSPI(AsyncAdapter[SPIDescriptor, bytes]):
    """Async SPI adapter, same parameters as SPI"""

    def __init__(
        self,
        bus: str | SPIBridge,
        cs: int | None = None,
        *,
        mode: int | None = None,
        speed_hz: int | None = None,
        bits_per_word: int | None = None,
        timeout: TimeoutParameterType = DEFAULT,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        super().__init__(
            _backend(bus, cs, SPISettings(mode, speed_hz, bits_per_word)),
            TrivialFramer(),
            timeout,
            alias=alias,
            auto_open=auto_open,
        )

    @staticmethod
    def list_buses() -> list[str]:
        """See SPI.list_buses"""
        return list_spi_devices()

    async def transfer(self, data: bytes) -> bytes:
        """See SPI.transfer"""
        return await self.query(data)
