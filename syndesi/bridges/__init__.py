"""
Bridges, drivers that provide a bus (I2C, SPI, serial) to the layers above them
"""

from .bridge import Bridge, I2CBridge, SerialBridge, SPIBridge
from .i2c import I2C
from .spi import SPI

__all__ = ["Bridge", "I2CBridge", "SPIBridge", "SerialBridge", "I2C", "SPI"]
