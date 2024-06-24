# auto.py
# Sébastien Deriaz
# 24.06.2024
#
# Automatic adapter function
# This function is used to automatically choose an adapter based on the user's input
# 192.168.1.1 -> IP
# COM4 -> Serial
# /dev/tty* -> Serial
# etc...
# If an adapter class is supplied, it is simply passed through
#
# Additionnaly, it is possible to do COM4:115200 so as to make the life of the user easier
# Same with /dev/ttyACM0:115200

from typing import Union
import re
from . import Adapter, IP, SerialPort

IP_PATTERN = '([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)(:[0-9]+)*'

WINDOWS_SERIAL_PATTERN = '(COM[0-9]+)(:[0-9]+)*'
LINUX_SERIAL_PATTERN = '(/dev/tty[a-zA-Z0-9]+)(:[0-9]+)*'

def auto_adapter(adapter_or_string : Union[Adapter, str]):
    if isinstance(adapter_or_string, Adapter):
        # Simply return it
        return adapter_or_string
    elif isinstance(adapter_or_string, str):
        # Parse it
        ip_match = re.match(IP_PATTERN, adapter_or_string)
        if ip_match:
            # Return an IP adapter
            return IP(address=ip_match.groups(0), port=ip_match.groups(1))
        elif re.match(WINDOWS_SERIAL_PATTERN, adapter_or_string):
            port, baudrate = re.match(WINDOWS_SERIAL_PATTERN, adapter_or_string).groups()
            return SerialPort(port=port, baudrate=int(baudrate))
        elif re.match(LINUX_SERIAL_PATTERN, adapter_or_string):
            port, baudrate = re.match(LINUX_SERIAL_PATTERN, adapter_or_string)
            return SerialPort(port=port, baudrate=int(baudrate))
        else:
            raise ValueError(f"Couldn't parse adapter description : {adapter_or_string}")

    else:
        raise ValueError(f"Invalid adapter : {adapter_or_string}")
