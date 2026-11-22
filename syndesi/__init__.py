"""
Syndesi module
"""

from importlib.metadata import version

__version__ = version("syndesi")

from .adapters.adapter import Adapter, AsyncAdapter
from .adapters.i2c import I2C, AsyncI2C, I2CTransfer
from .adapters.ip import IP, AsyncIP
from .adapters.ipserver import AsyncIPServer, Client, IPServer
from .adapters.serialport import AsyncSerialPort, Parity, SerialPort
from .adapters.spi import SPI, AsyncSPI
from .adapters.stop_conditions import (
    Continuation,
    FragmentSC,
    Length,
    Termination,
    Total,
)
from .adapters.visa import AsyncVisa, Visa
from .bridges import I2CBridge, LinuxI2C, LinuxSPI, SerialBridge, SPIBridge
from .drivers.driver import Driver, SubDriver
from .drivers.scpi_driver import SCPIDriver
from .drivers.tools import FlexibleEnum
from .protocols.delimited import AsyncDelimited, Delimited
from .protocols.modbus import (
    AsyncModbus,
    AsyncModbusServer,
    Modbus,
    ModbusMultiRegisterValue,
    ModbusServer,
)
from .protocols.protocol import AsyncProtocol, Protocol
from .protocols.raw import AsyncRaw, Raw
from .protocols.scpi import SCPI, AsyncSCPI

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
    # Protocols
    "AsyncProtocol",
    "Protocol",
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
    "SCPIDriver",
    "FlexibleEnum",
    # Buses
    "I2C",
    "AsyncI2C",
    "I2CTransfer",
    "SPI",
    "AsyncSPI",
    # Bridges
    "I2CBridge",
    "SPIBridge",
    "SerialBridge",
    "LinuxI2C",
    "LinuxSPI",
]
