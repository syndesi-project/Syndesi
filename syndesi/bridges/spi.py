# File : spi.py
# Author : Sébastien Deriaz
# License : GPL
"""
SPI, one device on an SPI bus provided by a bridge
"""

from __future__ import annotations

from ..tools.errors import AdapterReadError
from .bridge import SPIBridge


class SPI:
    """
    One device on an SPI bus

    Several SPI objects can share the same bridge, one per chip select. Their calls
    are run one at a time by the bridge

    Parameters
    ----------
    bridge : SPIBridge
        What provides the bus. The mode and clock are configured by its driver
    cs : int
        Chip select line of the device
    """

    def __init__(self, bridge: SPIBridge, cs: int = 0) -> None:
        self.bridge = bridge
        self.cs = cs

    def transfer(self, data: bytes) -> bytes:
        """Send data and return the bytes received meanwhile, as many as data"""
        received = self.bridge.run(self.bridge.spi_transfer, self.cs, bytes(data)).result()
        if len(received) != len(data):
            raise AdapterReadError(
                f"{self} : expected {len(data)} bytes, the bridge returned {len(received)}"
            )
        return received

    def write(self, data: bytes) -> None:
        """Send data, ignoring what is received"""
        self.transfer(data)

    def __str__(self) -> str:
        return f"SPI(cs {self.cs} on {self.bridge})"

    def __repr__(self) -> str:
        return self.__str__()
