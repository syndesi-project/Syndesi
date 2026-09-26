# File : auto.py
# Author : Sébastien Deriaz
# License : GPL
"""
Automatic adapter selection

Turns a descriptor string into the matching adapter, so that a driver or the CLI can
take ``'192.168.1.10:5025:TCP'`` or ``'/dev/ttyUSB0:115200'`` instead of an adapter

    192.168.1.1:502:TCP   -> IP
    COM4:115200           -> SerialPort
    /dev/ttyACM0:9600     -> SerialPort
    TCPIP0::1.2.3.4::INSTR -> Visa

An adapter passed in is returned unchanged
"""

from __future__ import annotations

import re
from typing import Any

from .adapter import Adapter, AsyncAdapter
from .engine import Descriptor
from .ip import AsyncIP, IP, IPDescriptor
from .serialport import AsyncSerialPort, SerialPort, SerialPortDescriptor

# Visa is optional, pyvisa may not be installed
try:
    from .visa import AsyncVisa, Visa, VisaDescriptor

    _VISA_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _VISA_AVAILABLE = False


def _descriptor_types() -> list[type[Descriptor]]:
    types: list[type[Descriptor]] = [SerialPortDescriptor, IPDescriptor]
    if _VISA_AVAILABLE:
        types.append(VisaDescriptor)
    return types


def adapter_descriptor_by_string(string_descriptor: str) -> Descriptor:
    """
    Return the descriptor matching a string

    Parameters
    ----------
    string_descriptor : str

    Returns
    -------
    descriptor : Descriptor
    """
    for descriptor_type in _descriptor_types():
        if re.match(descriptor_type.DETECTION_PATTERN, string_descriptor):
            return descriptor_type.from_string(string_descriptor)
    raise ValueError(f"Could not parse descriptor string : {string_descriptor}")


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

    descriptor = adapter_descriptor_by_string(adapter_or_string)

    if isinstance(descriptor, IPDescriptor):
        return IP(
            address=descriptor.address,
            port=descriptor.port,
            transport=descriptor.transport.value,
        )
    if isinstance(descriptor, SerialPortDescriptor):
        return SerialPort(port=descriptor.port, baudrate=descriptor.baudrate)
    if _VISA_AVAILABLE and isinstance(descriptor, VisaDescriptor):
        return Visa(descriptor=descriptor.descriptor)  # pylint: disable=no-member

    raise RuntimeError(f"Invalid descriptor : {descriptor}")


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

    descriptor = adapter_descriptor_by_string(adapter_or_string)

    if isinstance(descriptor, IPDescriptor):
        return AsyncIP(
            address=descriptor.address,
            port=descriptor.port,
            transport=descriptor.transport.value,
        )
    if isinstance(descriptor, SerialPortDescriptor):
        return AsyncSerialPort(port=descriptor.port, baudrate=descriptor.baudrate)
    if _VISA_AVAILABLE and isinstance(descriptor, VisaDescriptor):
        return AsyncVisa(descriptor=descriptor.descriptor)  # pylint: disable=no-member

    raise RuntimeError(f"Invalid descriptor : {descriptor}")
