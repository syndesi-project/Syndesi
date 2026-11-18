# File : auto.py
# Author : Sébastien Deriaz
# License : GPL
"""
Automatic adapter selection

Turns a descriptor string into the matching adapter, so that a driver or the CLI can
take ``'tcp:192.168.1.10:5025'`` or ``'serial:/dev/ttyUSB0:115200'`` instead of an
adapter. The scheme, before the first colon, names the adapter :

    tcp:192.168.1.1:502          -> IP
    udp:192.168.1.1:502          -> IP (UDP)
    serial:COM4:115200           -> SerialPort
    i2c:/dev/i2c-1@0x48          -> I2C (native bus, Linux)
    spi:/dev/spidev0.1           -> SPI (native bus, Linux)
    TCPIP0::1.2.3.4::INSTR       -> Visa, recognized by its own syntax

A bridge is an object, it can't be named in a string : i2c:MCP2221@0x20 is how its
adapter is displayed, it is built with I2C(MCP2221(...), 0x20). An IPServer accepts
clients instead of exchanging data, it isn't built from a string either

An adapter passed in is returned unchanged
"""

from __future__ import annotations

from typing import Any

from .adapter import Adapter, AsyncAdapter
from .engine import Descriptor
from .i2c import I2C, AsyncI2C, I2CDescriptor
from .ip import IP, AsyncIP, IPDescriptor
from .serialport import AsyncSerialPort, SerialPort, SerialPortDescriptor
from .spi import SPI, AsyncSPI, SPIDescriptor

# Visa is optional, pyvisa may not be installed
try:
    from .visa import AsyncVisa, Visa, VisaDescriptor

    _VISA_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _VISA_AVAILABLE = False

_DESCRIPTOR_TYPES: dict[str, type[Descriptor]] = {
    scheme: descriptor_type
    for descriptor_type in (IPDescriptor, SerialPortDescriptor, I2CDescriptor, SPIDescriptor)
    for scheme in descriptor_type.SCHEMES
}


def adapter_descriptor_by_string(string_descriptor: str) -> Descriptor:
    """
    Return the descriptor of a string, chosen by its scheme

    Parameters
    ----------
    string_descriptor : str

    Returns
    -------
    descriptor : Descriptor
    """
    scheme, separator, _ = string_descriptor.partition(":")
    descriptor_type = _DESCRIPTOR_TYPES.get(scheme) if separator else None
    if descriptor_type is not None:
        return descriptor_type.from_string(string_descriptor)
    if _VISA_AVAILABLE and "::" in string_descriptor:
        return VisaDescriptor.from_string(string_descriptor)
    schemes = ", ".join(f"{s}:" for s in _DESCRIPTOR_TYPES)
    raise ValueError(
        f"Could not parse descriptor string : {string_descriptor!r}, "
        f"expected one of {schemes} or a VISA resource"
    )


def _native_bus(descriptor: I2CDescriptor | SPIDescriptor) -> None:
    if not descriptor.bus.startswith("/dev/"):
        raise ValueError(
            f"{descriptor} : {descriptor.bus} is a bridge, pass the bridge object "
            "to the adapter instead of a string"
        )


def _build(string: str, asynchronous: bool) -> Any:
    """The adapter of a string, sync or async"""
    descriptor = adapter_descriptor_by_string(string)
    if isinstance(descriptor, IPDescriptor):
        if descriptor.server:
            raise ValueError(f"{descriptor} : an IPServer isn't built from a string")
        return (AsyncIP if asynchronous else IP)(
            descriptor.address, descriptor.port, descriptor.transport.value
        )
    if isinstance(descriptor, SerialPortDescriptor):
        return (AsyncSerialPort if asynchronous else SerialPort)(
            descriptor.port, descriptor.baudrate
        )
    if isinstance(descriptor, I2CDescriptor):
        _native_bus(descriptor)
        return (AsyncI2C if asynchronous else I2C)(descriptor.bus, descriptor.address)
    if isinstance(descriptor, SPIDescriptor):
        _native_bus(descriptor)
        return (AsyncSPI if asynchronous else SPI)(f"{descriptor.bus}.{descriptor.cs}")
    if _VISA_AVAILABLE and isinstance(descriptor, VisaDescriptor):
        return (AsyncVisa if asynchronous else Visa)(descriptor=descriptor.descriptor)
    raise RuntimeError(f"Invalid descriptor : {descriptor}")


def auto_adapter(adapter_or_string: Adapter[Any, bytes] | str) -> Adapter[Any, bytes]:
    """
    Return an adapter from a descriptor string, or the adapter it was given

    Parameters
    ----------
    adapter_or_string : Adapter or str
    """
    if isinstance(adapter_or_string, Adapter):
        return adapter_or_string
    if not isinstance(adapter_or_string, str):
        raise ValueError(f"Invalid adapter : {adapter_or_string!r}")
    adapter: Adapter[Any, bytes] = _build(adapter_or_string, asynchronous=False)
    return adapter


def auto_async_adapter(
    adapter_or_string: AsyncAdapter[Any, bytes] | str,
) -> AsyncAdapter[Any, bytes]:
    """
    Return an async adapter from a descriptor string, or the adapter it was given

    Parameters
    ----------
    adapter_or_string : AsyncAdapter or str
    """
    if isinstance(adapter_or_string, AsyncAdapter):
        return adapter_or_string
    if not isinstance(adapter_or_string, str):
        raise ValueError(f"Invalid adapter : {adapter_or_string!r}")
    adapter: AsyncAdapter[Any, bytes] = _build(adapter_or_string, asynchronous=True)
    return adapter
