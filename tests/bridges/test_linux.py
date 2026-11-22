"""
Native Linux buses : the ioctls are faked, the test checks what the kernel would receive

Real hardware is needed to test them end to end (i2c-dev, spidev)
"""

import ctypes
import os
import sys
import time

import pytest

from syndesi import (
    I2C,
    SPI,
    AsyncI2C,
    AsyncSPI,
    LinuxI2C,
    LinuxSPI
)
from syndesi.adapters.i2c import I2CDescriptor
from syndesi.adapters.spi import SPIDescriptor
from syndesi.bridges import linux
from syndesi.errors import AdapterWriteError

pytestmark = pytest.mark.skipif(
    not sys.platform.startswith("linux"), reason="native buses are Linux only"
)


class FakeKernel:
    """Records the ioctls, answers I2C reads with 0xA0, 0xA1, ... and SPI with ~tx"""

    def __init__(self) -> None:
        self.opened: list[str] = []
        self.calls: list[tuple[int, int, object]] = []
        self.error: OSError | None = None

    def open(self, path: str) -> int:
        """A real file descriptor, so that closing it is harmless"""
        self.opened.append(path)
        return os.open(os.devnull, os.O_RDONLY)

    def ioctl(self, fd: int, request: int, argument: object) -> None:
        self.calls.append((fd, request, argument))
        if self.error is not None:
            raise self.error
        if request == linux._I2C_RDWR:
            for i in range(argument.nmsgs):
                message = argument.msgs[i]
                if message.flags & linux._I2C_M_RD:
                    for j in range(message.len):
                        message.buf[j] = 0xA0 + j
        elif request == linux._spi_ioc_message(1):
            tx = (ctypes.c_uint8 * argument.len).from_address(argument.tx_buf)
            rx = (ctypes.c_uint8 * argument.len).from_address(argument.rx_buf)
            for j in range(argument.len):
                rx[j] = tx[j] ^ 0xFF


@pytest.fixture
def kernel(monkeypatch):
    fake = FakeKernel()
    monkeypatch.setattr(linux, "_open_device", fake.open)
    monkeypatch.setattr(linux, "_ioctl", fake.ioctl)
    return fake


def _messages(argument) -> list[tuple[int, int, bytes]]:
    return [
        (m.addr, m.flags, bytes(m.buf[: m.len]))
        for m in (argument.msgs[i] for i in range(argument.nmsgs))
    ]


def test_ioctl_structures_match_the_kernel():
    assert ctypes.sizeof(linux._I2CMsg) == 16
    assert ctypes.sizeof(linux._SpiIocTransfer) == 32
    assert linux._spi_ioc_message(1) == 0x40206B00


def test_linux_i2c_write_read(kernel):
    i2c = I2C(LinuxI2C("/dev/i2c-1"), 0x48)
    assert i2c.transfer(b"\x10", read_length=2) == b"\xa0\xa1"
    (fd, request, argument), = kernel.calls
    assert request == linux._I2C_RDWR
    assert _messages(argument) == [
        (0x48, 0, b"\x10"),
        (0x48, linux._I2C_M_RD, b"\xa0\xa1"),
    ]
    assert kernel.opened == ["/dev/i2c-1"]


def test_linux_i2c_plain_write_and_probe(kernel):
    i2c = I2C(LinuxI2C("/dev/i2c-1"), 0x50)
    i2c.write(b"\x00\x01")
    i2c.write(b"")  # address only, the device ACKs if it is there
    assert [_messages(call[2]) for call in kernel.calls] == [
        [(0x50, 0, b"\x00\x01")],
        [(0x50, 0, b"")],
    ]


def test_linux_i2c_error(kernel):
    kernel.error = OSError(121, "Remote I/O error")
    with pytest.raises(AdapterWriteError, match="Remote I/O error"):
        I2C(LinuxI2C("/dev/i2c-1"), 0x48).write(b"\x00")


def test_path_shares_one_bridge_per_bus(kernel):
    a = I2C("/dev/i2c-7", 0x48)
    b = I2C("/dev/i2c-7", 0x49)
    assert a.engine._backend.bridge is b.engine._backend.bridge
    assert str(a) == "i2c:/dev/i2c-7@0x48"
    a.write(b"\x00")
    b.write(b"\x00")
    assert kernel.opened == ["/dev/i2c-7"]


def test_linux_spi_transfer_and_settings(kernel):
    spi = SPI(LinuxSPI(0, mode=3, speed_hz=500_000), cs=1)
    assert spi.transfer(b"\x0f\xf0") == b"\xf0\x0f"
    requests = [call[1] for call in kernel.calls]
    assert requests == [
        linux._SPI_IOC_WR_MODE,
        linux._SPI_IOC_WR_MAX_SPEED_HZ,
        linux._spi_ioc_message(1),
    ]
    assert kernel.calls[0][2].value == 3
    assert kernel.calls[2][2].speed_hz == 500_000
    assert kernel.opened == ["/dev/spidev0.1"]


def test_spi_path(kernel):
    spi = SPI("/dev/spidev1.2")
    assert str(spi) == "spi:/dev/spidev1.2"
    assert spi.transfer(b"\x00") == b"\xff"
    assert kernel.opened == ["/dev/spidev1.2"]
    with pytest.raises(ValueError):
        SPI("/dev/spidev1.2", cs=0)


def test_spi_settings_per_chip_select(kernel):
    """Two devices of the same bus, each with its own mode and clock"""
    adc = SPI("/dev/spidev0.0", mode=1, speed_hz=1_000_000)
    flash = SPI("/dev/spidev0.1", mode=0)
    assert adc.engine._backend.bridge is flash.engine._backend.bridge
    adc.transfer(b"\x00")
    flash.transfer(b"\x00")
    modes = [
        (call[0], call[2].value)
        for call in kernel.calls
        if call[1] == linux._SPI_IOC_WR_MODE
    ]
    assert [mode for _, mode in modes] == [1, 0]
    assert modes[0][0] != modes[1][0]  # Two device files
    speeds = [call[2].speed_hz for call in kernel.calls if call[1] == linux._spi_ioc_message(1)]
    assert speeds == [1_000_000, 0]  # 0 : the clock already configured


def test_spi_settings_over_bus_defaults(kernel):
    bridge = LinuxSPI(2, mode=3, speed_hz=500_000)
    spi = SPI(bridge, cs=0, speed_hz=2_000_000)
    assert bridge.settings(0) == linux.SPISettings(3, 2_000_000, None)
    assert bridge.settings(1) == linux.SPISettings(3, 500_000, None)
    spi.transfer(b"\x00")
    assert kernel.calls[-1][2].speed_hz == 2_000_000


def test_spi_settings_applied_to_an_open_file(kernel):
    first = SPI("/dev/spidev3.0")
    first.transfer(b"\x00")
    kernel.calls.clear()
    SPI("/dev/spidev3.0", mode=2)
    assert [(call[1], call[2].value) for call in kernel.calls] == [
        (linux._SPI_IOC_WR_MODE, 2)
    ]


def test_spi_settings_are_checked(kernel):
    with pytest.raises(ValueError):
        SPI("/dev/spidev0.0", mode=4)
    with pytest.raises(ValueError):
        SPI("/dev/spidev0.0", speed_hz=0)

def test_descriptors_round_trip():
    for string in ("i2c:/dev/i2c-1@0x48", "i2c:MCP2221@0x20"):
        assert str(I2CDescriptor.from_string(string)) == string
    for string in ("spi:/dev/spidev0.1", "spi:MyBoard.3"):
        assert str(SPIDescriptor.from_string(string)) == string
    assert I2CDescriptor.from_string("i2c:/dev/i2c-1@72").address == 0x48
    with pytest.raises(ValueError):
        I2CDescriptor.from_string("i2c:/dev/i2c-1@0x80")


def _terminal(argv: list[str]):
    from syndesi.cli.terminal import Terminal  # pylint: disable=import-outside-toplevel

    terminal = Terminal(argv)
    printed: list[tuple[str, object]] = []
    terminal.shell.print = lambda text, style=None: printed.append((text, style))
    terminal.adapter.open()
    return terminal, printed


def _wait_for(printed, timeout=2.0):
    end = time.time() + timeout
    while not printed and time.time() < end:
        time.sleep(0.01)
    return printed


def test_cli_i2c_and_spi(kernel):
    terminal, printed = _terminal(["i2c", "/dev/i2c-1", "0x48", "--read", "2"])
    terminal.on_command("10")  # hex and no termination by default
    assert _wait_for(printed) == [("A0 A1", None)]
    assert _messages(kernel.calls[-1][2])[0] == (0x48, 0, b"\x10")

    terminal, printed = _terminal(["spi", "/dev/spidev0.0"])
    terminal.on_command("0f f0")
    assert _wait_for(printed) == [("F0 0F", None)]


def test_cli_prints_bridge_errors(kernel):
    terminal, printed = _terminal(["i2c", "/dev/i2c-1", "0x50"])
    kernel.error = OSError(121, "Remote I/O error")
    terminal.on_command("00")
    assert "Remote I/O error" in printed[0][0]
