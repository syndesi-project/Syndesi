# File : i2c.py
# Author : Sébastien Deriaz
# License : GPL
"""
I2C, one device on an I2C bus provided by a bridge
"""

from __future__ import annotations

from ..tools.errors import AdapterReadError
from .bridge import I2CBridge


class I2C:
    """
    One device on an I2C bus

    Several I2C objects can share the same bridge, one per address. Their calls are
    run one at a time by the bridge

    Parameters
    ----------
    bridge : I2CBridge
        What provides the bus (MCP2221, custom board, ...)
    address : int
        7-bit address of the device
    """

    def __init__(self, bridge: I2CBridge, address: int) -> None:
        if not 0 <= address <= 0x7F:
            raise ValueError(f"Invalid I2C address : {address:#x}, must be 7-bit")
        self.bridge = bridge
        self.address = address

    def write(self, data: bytes) -> None:
        """Write data to the device"""
        self._transfer(data, 0)

    def read(self, length: int) -> bytes:
        """Read length bytes from the device"""
        return self._transfer(b"", length)

    def write_read(self, data: bytes, length: int) -> bytes:
        """Write data, then read length bytes with a repeated start (register read)"""
        return self._transfer(data, length)

    def _transfer(self, data: bytes, length: int) -> bytes:
        if length < 0:
            raise ValueError(f"Invalid read length : {length}")
        received = self.bridge.run(
            self.bridge.i2c_transfer, self.address, bytes(data), length
        ).result()
        if len(received) != length:
            raise AdapterReadError(
                f"{self} : expected {length} bytes, the bridge returned {len(received)}"
            )
        return received

    def __str__(self) -> str:
        return f"I2C({self.address:#04x} on {self.bridge})"

    def __repr__(self) -> str:
        return self.__str__()
