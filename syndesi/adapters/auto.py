# File : auto.py
# Author : Sébastien Deriaz
# License : GPL

"""
Automatic adapter function
This function is used to automatically choose an adapter based on the user's input
192.168.1.1 -> IP
COM4 -> Serial
/dev/tty* -> Serial
etc...
If an adapter class is supplied, it is passed through

Additionnaly, it is possible to do COM4:115200 so as to make the life of the user easier
Same with /dev/ttyACM0:115200
"""


import re

from syndesi.component import Descriptor

from .adapter import Adapter
from .ip import IP, IPDescriptor
from .serialport import SerialPort, SerialPortDescriptor
from .visa import Visa, VisaDescriptor

descriptors: list[type[Descriptor]] = [
    SerialPortDescriptor,
    IPDescriptor,
    VisaDescriptor,
]


def adapter_descriptor_by_string(string_descriptor: str) -> Descriptor:
    """
    Return a corresponding adapter descriptor from a string

    Parameters
    ----------
    string_descriptor : str

    Returns
    -------
    descriptor : Descriptor
    """
    for descriptor in descriptors:
        if re.match(descriptor.DETECTION_PATTERN, string_descriptor):
            x = descriptor.from_string(string_descriptor)
            return x
    raise ValueError(f"Could not parse descriptor string : {string_descriptor}")


def auto_adapter(adapter_or_string: Adapter | str) -> Adapter:
    """
    Create an adapter from a string or an adapter

    - <int>.<int>.<int>.<int>[:<int>] -> IP
    - x.y[:<int>] -> IP
    - COM<int> -> SerialPort
    - /dev/tty[ACM|USB]<int> -> SerialPort

    """
    if isinstance(adapter_or_string, Adapter):
        # Simply return it
        return adapter_or_string

    if isinstance(adapter_or_string, str):
        descriptor = adapter_descriptor_by_string(adapter_or_string)
        if isinstance(descriptor, IPDescriptor):
            return IP(
                address=descriptor.address,
                port=descriptor.port,
                transport=descriptor.transport.value,
            )
        if isinstance(descriptor, SerialPortDescriptor):
            return SerialPort(port=descriptor.port, baudrate=descriptor.baudrate)
        if isinstance(descriptor, VisaDescriptor):
            return Visa(descriptor=descriptor.descriptor)

        raise RuntimeError(f"Invalid descriptor : {descriptor}")

    raise ValueError(f"Invalid adapter : {adapter_or_string}")
