"""Descriptor strings : scheme:target, read back by from_string"""

from syndesi.adapters.ip import IPDescriptor
from syndesi.adapters.serialport import SerialPortDescriptor

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
