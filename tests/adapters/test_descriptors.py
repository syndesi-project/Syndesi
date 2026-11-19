"""Descriptor strings : scheme:target, read back by from_string and auto_adapter"""

import pytest

from syndesi import IP, SerialPort, auto_adapter, auto_async_adapter
from syndesi.adapters.auto import adapter_descriptor_by_string
from syndesi.adapters.ip import AsyncIP, IPDescriptor
from syndesi.adapters.serialport import SerialPortDescriptor


@pytest.mark.parametrize(
    "string",
    [
        "tcp:192.168.1.1:502",
        "udp:my-scope.local:5025",
        "tcp-server:0.0.0.0:5025",
        "udp-server:0.0.0.0:5025",
        "tcp:[::1]:502",
        "tcp:192.168.1.1",
        "serial:COM4:115200",
        "serial:/dev/ttyUSB0:9600",
        "serial:/dev/ttyUSB0",
        "i2c:/dev/i2c-1@0x48",
        "i2c:MCP2221#2@0x20",
        "spi:/dev/spidev0.1",
    ],
)
def test_round_trip(string):
    assert str(adapter_descriptor_by_string(string)) == string


def test_ip_descriptor():
    d = IPDescriptor.from_string("udp-server:[fe80::1]:5025")
    assert (d.address, d.port, d.transport, d.server) == (
        "fe80::1",
        5025,
        IPDescriptor.Transport.UDP,
        True,
    )
    assert IPDescriptor.from_string("tcp:host").port is None


def test_serial_descriptor():
    d = SerialPortDescriptor.from_string("serial:COM4:115200")
    assert (d.port, d.baudrate) == ("COM4", 115200)
    assert SerialPortDescriptor.from_string("serial:COM4").baudrate is None


@pytest.mark.parametrize(
    "string",
    [
        # The former syntax, without scheme
        "192.168.1.1:502:TCP",
        "COM4:115200",
        "/dev/i2c-1@0x48",
        "/dev/spidev0.1",
        # Invalid targets
        "tcp:",
        "tcp:1.2.3.4:port",
        "tcp:[::1]502",
        "serial:",
        "i2c:/dev/i2c-1",
        "i2c:/dev/i2c-1@0x80",
        "spi:/dev/spidev0",
        "unknown:thing",
    ],
)
def test_invalid(string):
    with pytest.raises(ValueError):
        adapter_descriptor_by_string(string)


def test_auto_adapter():
    ip = auto_adapter("tcp:127.0.0.1:5025")
    assert isinstance(ip, IP) and str(ip) == "tcp:127.0.0.1:5025"
    assert isinstance(auto_async_adapter("udp:127.0.0.1:5025"), AsyncIP)
    serial = auto_adapter("serial:/dev/ttyUSB0:115200")
    assert isinstance(serial, SerialPort) and serial.descriptor.baudrate == 115200


@pytest.mark.parametrize(
    "string", ["tcp-server:0.0.0.0:5025", "i2c:MCP2221@0x20", "spi:MyBoard.1"]
)
def test_auto_adapter_refuses_what_a_string_cant_build(string):
    with pytest.raises(ValueError):
        auto_adapter(string)
