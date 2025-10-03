# File : auto.py
# Author : Sébastien Deriaz
# License : GPL
#
# Automatic adapter function
# This function is used to automatically choose an adapter based on the user's input
# 192.168.1.1 -> IP
# COM4 -> Serial
# /dev/tty* -> Serial
# etc...
# If an adapter class is supplied, it is passed through
#
# Additionnaly, it is possible to do COM4:115200 so as to make the life of the user easier
# Same with /dev/ttyACM0:115200


from .adapter import Adapter
from .backend.descriptors import (
    IPDescriptor,
    SerialPortDescriptor,
    VisaDescriptor,
    adapter_descriptor_by_string,
)
from .ip import IP
from .serialport import SerialPort
from .visa import Visa


def auto_adapter(adapter_or_string: Adapter | str) -> Adapter:
    if isinstance(adapter_or_string, Adapter):
        # Simply return it
        return adapter_or_string

    elif isinstance(adapter_or_string, str):
        descriptor = adapter_descriptor_by_string(adapter_or_string)
        if isinstance(descriptor, IPDescriptor):
            return IP(
                address=descriptor.address,
                port=descriptor.port,
                transport=descriptor.transport.value,
            )
        elif isinstance(descriptor, SerialPortDescriptor):
            return SerialPort(port=descriptor.port, baudrate=descriptor.baudrate)
        elif isinstance(descriptor, VisaDescriptor):
            return Visa(descriptor=descriptor.descriptor)
        else:
            raise RuntimeError(f"Invalid descriptor : {descriptor}")

    else:
        raise ValueError(f"Invalid adapter : {adapter_or_string}")
