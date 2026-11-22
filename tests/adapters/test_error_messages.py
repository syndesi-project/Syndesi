"""
Error messages say what went wrong and what to do about it

And an error raised to the caller is not printed : the caller may handle it
"""

import asyncio
import errno
import logging
import os
import socket
import stat
from types import SimpleNamespace

import pytest
import serial

from syndesi import IP, SCPI, AsyncIP, Delimited, SerialPort, Visa
from syndesi.adapters import ip as ip_module
from syndesi.adapters import serialport as serial_module
from syndesi.adapters import visa as visa_module
from syndesi.errors import AdapterOpenError, ProtocolWriteError
from syndesi.tools import hints

HOST = "127.0.0.1"


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


# str and bytes


def test_str_on_adapter_write():
    with pytest.raises(TypeError, match=r"IP\.write\(\) sends bytes, not str : write b'hello\\n'"):
        IP(HOST, 1, auto_open=False).write("hello\n")


def test_non_ascii_str_on_adapter_query():
    with pytest.raises(TypeError, match=r"write 'héllo'\.encode\(\)"):
        IP(HOST, 1, auto_open=False).query("héllo")


def test_str_on_async_adapter_write():
    async def main() -> None:
        with pytest.raises(TypeError, match=r"Delimited\(AsyncIP\(\.\.\.\)\)"):
            await AsyncIP(HOST, 1, auto_open=False).write("hello")

    asyncio.run(main())


def test_bytes_on_text_protocol():
    with pytest.raises(ProtocolWriteError, match="not bytes : write 'hello'"):
        Delimited(IP(HOST, _closed_port())).write(b"hello")


def test_number_on_text_protocol():
    with pytest.raises(ProtocolWriteError, match=r"not float : write str\(3\.3\)"):
        SCPI(IP(HOST, _closed_port())).write(3.3)


# Incomplete descriptors


def test_serial_without_baudrate():
    with pytest.raises(AdapterOpenError, match=r"SerialPort\('/dev/null', 115200\)"):
        SerialPort("/dev/null").open()


# IP


@pytest.mark.parametrize(
    "error, expected",
    [
        (ConnectionRefusedError(), "connection refused. Nothing listens on 10.0.0.1:5025"),
        (TimeoutError(), "no answer from 10.0.0.1 within 2.0 seconds"),
        (socket.gaierror(-2, "Name or service not known"), "unknown host '10.0.0.1'"),
        (OSError(errno.EHOSTUNREACH, "No route to host"), "No route to host. Check"),
    ],
)
def test_ip_open_messages(error, expected):
    descriptor = IP("10.0.0.1", 5025, auto_open=False).descriptor
    assert expected in ip_module._open_error_message(descriptor, error, 2.0)


def test_ip_refused_end_to_end():
    with pytest.raises(AdapterOpenError, match="connection refused"):
        IP(HOST, _closed_port()).open()


# Serial


def test_serial_not_found_lists_ports(monkeypatch):
    monkeypatch.setattr(
        serial_module,
        "describe_ports",
        lambda: {"/dev/ttyACM0": "Arduino Uno", "/dev/ttyUSB1": ""},
    )
    error = serial.SerialException(errno.ENOENT, "could not open port /dev/ttyUSB9")
    message = serial_module._open_error_message("/dev/ttyUSB9", error)
    assert message == (
        "Port '/dev/ttyUSB9' was not found. "
        "Available ports : /dev/ttyACM0 (Arduino Uno), /dev/ttyUSB1"
    )


def test_describe_ports(monkeypatch):
    def port(device, description, product=None, manufacturer=None):
        name = device.rsplit("/", 1)[-1]
        return SimpleNamespace(
            device=device,
            name=name,
            description=description,
            product=product,
            manufacturer=manufacturer,
        )

    ports = [
        port("/dev/ttyACM0", "Arduino Uno"),
        port("/dev/ttyUSB0", "n/a", product="CP2102 USB to UART"),
        port("/dev/ttyUSB1", "ttyUSB1"),
    ]
    monkeypatch.setattr(serial_module, "comports", lambda: ports)
    monkeypatch.setattr(serial_module.sys, "platform", "linux")
    assert serial_module.describe_ports() == {
        "/dev/ttyACM0": "Arduino Uno",
        "/dev/ttyUSB0": "CP2102 USB to UART",
        "/dev/ttyUSB1": "",
    }


def test_serial_not_found_without_ports(monkeypatch):
    monkeypatch.setattr(serial_module, "describe_ports", lambda: {})
    error = serial.SerialException(errno.ENOENT, "could not open port /dev/ttyUSB9")
    assert "is the device plugged in" in serial_module._open_error_message("/dev/ttyUSB9", error)


@pytest.mark.parametrize(
    "error",
    [
        serial.SerialException(errno.EACCES, "could not open port /dev/ttyUSB0"),
        # Windows : no errno, the text of the Windows error
        serial.SerialException(
            "could not open port 'COM3': PermissionError(13, 'Access is denied.', None, 5)"
        ),
    ],
)
def test_serial_permission_denied(monkeypatch, error):
    monkeypatch.setattr(serial_module, "permission_hint", lambda port: "HINT")
    message = serial_module._open_error_message("/dev/ttyUSB0", error)
    assert message == "Cannot open /dev/ttyUSB0 : permission denied\nHINT"


def test_serial_busy():
    error = serial.SerialException(
        errno.EAGAIN, "Could not exclusively lock port /dev/ttyUSB0"
    )
    message = serial_module._open_error_message("/dev/ttyUSB0", error)
    assert "port busy" in message
    assert "open in another program" in message


# Permission hints


def _fake_stat(monkeypatch, mode: int, gid: int, groups: list[int], group: str) -> None:
    result = os.stat_result((stat.S_IFCHR | mode, 0, 0, 0, 0, gid, 0, 0, 0, 0))
    monkeypatch.setattr(hints.sys, "platform", "linux")
    monkeypatch.setattr(hints.os, "stat", lambda path: result)
    monkeypatch.setattr(hints.os, "getgroups", lambda: groups)
    monkeypatch.setattr(hints, "_group_name", lambda g: group)


def test_hint_group_to_join(monkeypatch):
    _fake_stat(monkeypatch, 0o660, 20, [1000], "dialout")
    hint = hints.permission_hint("/dev/ttyUSB0")
    assert "belongs to the group 'dialout'" in hint
    assert "sudo usermod -aG dialout $USER" in hint


def test_hint_group_joined_but_session_too_old(monkeypatch):
    _fake_stat(monkeypatch, 0o660, 20, [1000, 20], "dialout")
    assert "log out and back in" in hints.permission_hint("/dev/ttyUSB0")


def test_hint_root_only_gives_a_udev_rule(monkeypatch):
    _fake_stat(monkeypatch, 0o600, 0, [1000], "root")
    hint = hints.permission_hint("/dev/i2c-1")
    assert 'KERNEL=="i2c-[0-9]*", GROUP="i2c", MODE="0660"' in hint
    assert "sudo usermod -aG i2c $USER" in hint


def test_hint_windows_port_in_use(monkeypatch):
    monkeypatch.setattr(hints.sys, "platform", "win32")
    assert "open in another program" in hints.permission_hint("COM3")


# VISA


def test_visa_without_library(monkeypatch):
    def no_library() -> None:
        raise ValueError("Could not locate a VISA implementation")

    monkeypatch.setattr(visa_module.pyvisa, "ResourceManager", no_library)
    with pytest.raises(AdapterOpenError, match="pip install pyvisa-py"):
        Visa("GPIB0::1::INSTR")


# Logging


def test_caught_open_error_is_not_printed(caplog):
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(AdapterOpenError):
            IP(HOST, _closed_port()).open()
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

