# File : i2c.py
# Author : Sébastien Deriaz
# License : GPL
"""
I2C adapter, one device on an I2C bus

The bus is the machine's own (I2C("/dev/i2c-1", 0x48), Linux only) or provided by a
bridge (I2C(MCP2221(...), 0x48)). Both work the same way, see BusBackend

Each write is a transaction. A plain bytes write only writes, an I2CTransfer also reads
read_length bytes after it, with a repeated start, and those come back as a frame :

    i2c.write(b"\\x01\\x60")                  # write a register
    i2c.transfer(b"\\x00", read_length=2)     # read a register
    i2c.query(I2CTransfer(b"\\x00", 2))       # the same, what a protocol would write
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..bridges.bridge import I2CBridge
from ..bridges.linux import linux_i2c, list_i2c_buses
from ..errors import AdapterReadError
from ..tools.others import DEFAULT
from .adapter import Adapter, AsyncAdapter
from .bus import BusBackend
from .engine import Descriptor
from .framer import TrivialFramer
from .utils import TimeoutParameterType


class I2CTransfer(bytes):
    """
    Bytes to write, followed by read_length bytes to read with a repeated start

    A bytes subclass : it travels through the engine, the protocols and the traces like
    any data, the I2C backend is the only one to look at read_length

    Parameters
    ----------
    data : bytes
        Written first, b"" for a plain read
    read_length : int
    """

    read_length: int

    def __new__(cls, data: bytes = b"", read_length: int = 0) -> I2CTransfer:
        if read_length < 0:
            raise ValueError(f"Invalid read length : {read_length}")
        transfer = super().__new__(cls, data)
        transfer.read_length = read_length
        return transfer

    def __repr__(self) -> str:
        return f"I2CTransfer({bytes(self)!r}, read_length={self.read_length})"


@dataclass
class I2CDescriptor(Descriptor):
    """
    Bus and address of an I2C device, written i2c:bus@address : i2c:/dev/i2c-1@0x48

    bus is the device file of a native bus, or the name of the bridge (i2c:MCP2221@0x20)
    """

    SCHEMES = ("i2c",)
    bus: str
    address: int

    def __post_init__(self) -> None:
        if not 0 <= self.address <= 0x7F:
            raise ValueError(f"Invalid I2C address : {self.address:#x}, must be 7-bit")

    @staticmethod
    def from_string(string: str) -> I2CDescriptor:
        _, target = I2CDescriptor.split_scheme(string)
        match = re.match(r"^(.+)@(0x[0-9a-fA-F]+|\d+)$", target)
        if match is None:
            raise ValueError(
                f"Invalid descriptor : {string!r}, expected i2c:bus@address"
            )
        return I2CDescriptor(match.group(1), int(match.group(2), 0))

    def is_initialized(self) -> bool:
        return True

    def __str__(self) -> str:
        return f"i2c:{self.bus}@{self.address:#04x}"


class I2CBackend(BusBackend[I2CDescriptor]):
    """
    Runs the I2C transactions of one device on its bridge

    Parameters
    ----------
    bridge : I2CBridge
    descriptor : I2CDescriptor
    """

    def __init__(self, bridge: I2CBridge, descriptor: I2CDescriptor) -> None:
        super().__init__(bridge, descriptor)
        self._i2c_bridge = bridge

    def transfer(self, data: bytes) -> bytes:
        length = data.read_length if isinstance(data, I2CTransfer) else 0
        received = self._i2c_bridge.i2c_transfer(
            self.descriptor.address, bytes(data), length
        )
        if len(received) != length:
            raise AdapterReadError(
                f"{self.descriptor} : expected {length} bytes, "
                f"the bridge returned {len(received)}"
            )
        return received


def _backend(bus: str | I2CBridge, address: int) -> I2CBackend:
    bridge = bus if isinstance(bus, I2CBridge) else linux_i2c(bus)
    return I2CBackend(bridge, I2CDescriptor(str(bridge), address))


class I2C(Adapter[I2CDescriptor, bytes]):
    """
    One device on an I2C bus

    Several I2C adapters can share a bus, one per address. Their transactions are run
    one at a time by the bridge

    Parameters
    ----------
    bus : str or I2CBridge
        /dev/i2c-N for a native bus (Linux), or the bridge that provides the bus
        (MCP2221, custom board, ...)
    address : int
        7-bit address of the device
    timeout : float, None or DEFAULT
    alias : str
    auto_open : bool
        See Adapter
    """

    def __init__(
        self,
        bus: str | I2CBridge,
        address: int,
        *,
        timeout: TimeoutParameterType = DEFAULT,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        super().__init__(
            _backend(bus, address),
            TrivialFramer(),
            timeout,
            alias=alias,
            auto_open=auto_open,
        )

    @staticmethod
    def list_buses() -> list[str]:
        """The native I2C buses, /dev/i2c-N (Linux)"""
        return list_i2c_buses()

    def transfer(self, data: bytes = b"", read_length: int = 0) -> bytes:
        """
        Write data, then read read_length bytes with a repeated start

        Either part can be empty : read_length=0 only writes, data=b"" only reads
        """
        if read_length == 0:
            self.write(data)
            return b""
        return self.query(I2CTransfer(data, read_length))


class AsyncI2C(AsyncAdapter[I2CDescriptor, bytes]):
    """Async I2C adapter, same parameters as I2C"""

    def __init__(
        self,
        bus: str | I2CBridge,
        address: int,
        *,
        timeout: TimeoutParameterType = DEFAULT,
        alias: str = "",
        auto_open: bool = True,
    ) -> None:
        super().__init__(
            _backend(bus, address),
            TrivialFramer(),
            timeout,
            alias=alias,
            auto_open=auto_open,
        )

    @staticmethod
    def list_buses() -> list[str]:
        """See I2C.list_buses"""
        return list_i2c_buses()

    async def transfer(self, data: bytes = b"", read_length: int = 0) -> bytes:
        """See I2C.transfer"""
        if read_length == 0:
            await self.write(data)
            return b""
        return await self.query(I2CTransfer(data, read_length))
