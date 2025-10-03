# File : descriptors.py
# Author : Sébastien Deriaz
# License : GPL
#
# Descriptors are classes that describe how an adapter is connected to its device.
# Depending on the protocol, they can hold strings, integers or enums

import re
from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum


class Descriptor:
    DETECTION_PATTERN = ""

    def __init__(self) -> None:
        return None

    @staticmethod
    @abstractmethod
    def from_string(string: str) -> "Descriptor":
        pass

    @abstractmethod
    def is_initialized(self) -> bool:
        pass


@dataclass
class SerialPortDescriptor(Descriptor):
    DETECTION_PATTERN = r"(COM\d+|/dev[/\w\d]+):\d+"
    port: str
    baudrate: int | None = None

    @staticmethod
    def from_string(string: str) -> "SerialPortDescriptor":
        parts = string.split(":")
        port = parts[0]
        baudrate = int(parts[1])
        return SerialPortDescriptor(port, baudrate)

    def set_default_baudrate(self, baudrate: int) -> bool:
        if self.baudrate is not None:
            self.baudrate = baudrate
            return True
        else:
            return False

    def __str__(self) -> str:
        return f"{self.port}:{self.baudrate}"

    def is_initialized(self) -> bool:
        return self.baudrate is not None


@dataclass
class IPDescriptor(Descriptor):
    class Transport(Enum):
        TCP = "TCP"
        UDP = "UDP"

        @classmethod
        def from_str(cls, value: str) -> "IPDescriptor":
            for member in cls:
                if member.value.lower() == value.lower():
                    return member  # type: ignore # TODO : Check this
            raise ValueError(f"{value} is not a valid {cls.__name__}")

    DETECTION_PATTERN = r"(\d+.\d+.\d+.\d+|[\w\.]+):\d+:(UDP|TCP)"
    address: str
    transport: Transport
    port: int | None = None
    # transport: Transport | None = None

    @staticmethod
    def from_string(string: str) -> "IPDescriptor":
        parts = string.split(":")
        address = parts[0]
        port = int(parts[1])
        transport = IPDescriptor.Transport(parts[2])
        return IPDescriptor(address, transport, port)

    def __str__(self) -> str:
        return f"{self.address}:{self.port}:{self.Transport(self.transport).value}"

    def is_initialized(self) -> bool:
        return self.port is not None and self.transport is not None


@dataclass
class VisaDescriptor(Descriptor):
    # VISA Resource Address Examples
    # GPIB (IEEE-488)
    # GPIB0::14::INSTR
    # # Serial (RS-232 or USB-Serial)
    # ASRL1::INSTR                  # Windows COM1
    # ASRL/dev/ttyUSB0::INSTR       # Linux USB serial port
    #
    # # TCPIP INSTR (LXI/VXI-11/HiSLIP-compatible instruments)
    # TCPIP0::192.168.1.100::INSTR
    # TCPIP0::my-scope.local::inst0::INSTR
    #
    # # TCPIP SOCKET (Raw TCP communication)
    # TCPIP0::192.168.1.42::5025::SOCKET
    #
    # # USB (USBTMC-compliant instruments)
    # USB0::0x0957::0x1796::MY12345678::INSTR
    #
    # # VXI (Legacy modular instruments)
    # VXI0::2::INSTR
    #
    # # PXI (Modular instrument chassis)
    # PXI0::14::INSTR
    DETECTION_PATTERN = r"([A-Z]+)(\d*|\/[^:]+)?::([^:]+)(?:::([^:]+))?(?:::([^:]+))?(?:::([^:]+))?::(INSTR|SOCKET)"

    descriptor: str

    class Interface(Enum):
        GPIB = "GPIB"
        SERIAL = "ASRL"
        TCP = "TCPIP"
        USB = "USB"
        VXI = "VXI"
        PXI = "PXI"

    @staticmethod
    def from_string(string: str) -> "VisaDescriptor":
        if re.match(VisaDescriptor.DETECTION_PATTERN, string):
            return VisaDescriptor(descriptor=string)
        else:
            raise ValueError(f"Could not parse descriptor : {string}")

    def __str__(self) -> str:
        return self.descriptor

    def is_initialized(self) -> bool:
        return True


descriptors: list[type[Descriptor]] = [
    SerialPortDescriptor,
    IPDescriptor,
    VisaDescriptor,
]


def adapter_descriptor_by_string(string_descriptor: str) -> Descriptor:
    for descriptor in descriptors:
        if re.match(descriptor.DETECTION_PATTERN, string_descriptor):
            x = descriptor.from_string(string_descriptor)
            return x
    raise ValueError(f"Could not parse descriptor string : {string_descriptor}")
