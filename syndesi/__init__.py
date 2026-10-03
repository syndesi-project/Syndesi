"""
Syndesi module
"""

from .adapters.auto import auto_adapter, auto_async_adapter
from .adapters.ip import IP, AsyncIP
from .adapters.ipserver import AsyncIPServer, Client, IPServer
from .adapters.serialport import AsyncSerialPort, Parity, SerialPort
from .protocols.delimited import AsyncDelimited, Delimited
from .protocols.modbus import AsyncModbus, Modbus, ModbusSerialType
from .protocols.raw import AsyncRaw, Raw
from .protocols.scpi import SCPI, AsyncSCPI
from .adapters.visa import AsyncVisa, Visa

__all__ = [
    # Adapters
    "IP",
    "AsyncIP",
    "SerialPort",
    "AsyncSerialPort",
    "Parity",
    "IPServer",
    "AsyncIPServer",
    "Client",
    "auto_adapter",
    "auto_async_adapter",
    # Protocols
    "Delimited",
    "AsyncDelimited",
    "Raw",
    "AsyncRaw",
    "SCPI",
    "AsyncSCPI",
    "Modbus",
    "AsyncModbus",
    "ModbusSerialType",
    "Visa",
    "AsyncVisa"
]
