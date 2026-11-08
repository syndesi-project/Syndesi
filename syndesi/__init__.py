"""
Syndesi module
"""
from importlib.metadata import version
<<<<<<< HEAD

__version__ = version("syndesi")
=======
>>>>>>> dev

__version__ = version("syndesi")

from .adapters.adapter import Adapter, AsyncAdapter
from .adapters.auto import auto_adapter, auto_async_adapter
from .adapters.ip import IP, AsyncIP
from .adapters.ipserver import AsyncIPServer, Client, IPServer
from .adapters.serialport import AsyncSerialPort, Parity, SerialPort
from .adapters.stop_conditions import Continuation, FragmentSC, Length, Termination, Total
from .adapters.visa import AsyncVisa, Visa
from .protocols.protocol import Protocol, AsyncProtocol
from .protocols.delimited import AsyncDelimited, Delimited
from .protocols.modbus import (
    AsyncModbus,
    AsyncModbusServer,
    Modbus,
    ModbusMultiRegisterValue,
    ModbusServer,
)
from .protocols.raw import AsyncRaw, Raw
from .protocols.scpi import SCPI, AsyncSCPI
from .drivers.driver import Driver, SubDriver
from .drivers.scpi_driver import SCPIDriver

__all__ = [
    # Adapters
    "Adapter",
    "AsyncAdapter",
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
    "ModbusServer",
    "AsyncModbusServer",
    "ModbusMultiRegisterValue",
    "Visa",
    "AsyncVisa",
    # Stop conditions
    "Termination",
    "Continuation",
    "FragmentSC",
    "Length",
    "Total",
    # Drivers
    "Driver",
    "SubDriver",
    "SCPIDriver"
]
