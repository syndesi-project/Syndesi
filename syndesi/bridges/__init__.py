"""
Bridges, drivers that provide a bus (I2C, SPI, serial) to the adapters above them
"""

from .bridge import Bridge, I2CBridge, SerialBridge, SPIBridge
from .linux import LinuxI2C, LinuxSPI, SPISettings
from .mcp2221 import MCP2221

__all__ = [
    "Bridge",
    "I2CBridge",
    "SPIBridge",
    "SerialBridge",
    "LinuxI2C",
    "LinuxSPI",
    "SPISettings",
    "MCP2221",
]
