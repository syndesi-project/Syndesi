"""
MCP2221 bridge, against a simulated chip on a fake hidapi (see tests/conftest.py)

The simulation follows the MCP2221A datasheet (DS20005565) : it checks that the driver
speaks the protocol as documented. Real hardware is needed to test it end to end
"""

import asyncio
import re
import threading

import pytest

from syndesi import I2C, MCP2221, AsyncI2C
from syndesi.tools.errors import AdapterConfigurationError, AdapterWriteError

REPORT = 64
NACK_ADDRESS = 0x50


class SimulatedMCP2221:
    """
    The command set of the chip used by the driver

    One I2C device answers at 0x48 : a register memory, the first byte written sets the
    register pointer. Every other address NACKs
    """

    def __init__(self) -> None:
        self.memory = bytearray(256)
        self.pointer = 0
        self.state = 0x00
        self.nack = False
        self.divider: int | None = None
        self.write_buffer = b""
        self.write_remaining = 0
        self.read_data = b""
        self.read_nack = False
        self.commands: list[int] = []
        # GP0..GP3 SRAM settings : designation in bits 2:0 (0 = GPIO), bit 3 input,
        # bit 4 output value. From the factory, none is a GPIO
        self.gp_settings = [0x01, 0x01, 0x01, 0x01]
        self.lock = threading.Lock()

    def on_write(self, report: bytes) -> list[bytes]:
        assert report[0] == 0x00, "MCP2221 reports are unnumbered"
        assert len(report) == REPORT + 1, "Every command is a full 64 bytes report"
        request = report[1:]
        with self.lock:
            answer = bytearray(REPORT)
            answer[0] = request[0]
            self.commands.append(request[0])
            handler = getattr(self, f"_cmd_{request[0]:02x}", None)
            if handler is None:
                answer[1] = 0x01
            else:
                handler(request, answer)
            return [bytes(answer)]

    # Status / set parameters
    def _cmd_10(self, request: bytes, answer: bytearray) -> None:
        if request[2] == 0x10:  # cancel
            self.state = 0x00
            self.nack = False
            self.write_remaining = 0
            answer[2] = 0x10
        if request[3] == 0x20:  # set speed
            self.divider = request[4]
            answer[3] = 0x20
        answer[8] = self.state
        answer[20] = 0x40 if self.nack else 0x00

    def _write(self, request: bytes, answer: bytearray, no_stop: bool) -> None:
        length = request[1] | request[2] << 8
        address = request[3] >> 1
        if self.write_remaining == 0:
            self.write_remaining = length
            self.write_buffer = b""
            self.nack = False
        chunk = request[4 : 4 + min(60, self.write_remaining)]
        self.write_buffer += chunk
        self.write_remaining -= len(chunk)
        answer[1] = 0x00
        if address != 0x48:
            self.nack = True
            self.state = 0x25
            self.write_remaining = 0
            return
        if self.write_remaining == 0:
            data = self.write_buffer
            if data:
                self.pointer = data[0]
                self.memory[self.pointer : self.pointer + len(data) - 1] = data[1:]
            self.state = 0x45 if no_stop else 0x00

    def _cmd_90(self, request: bytes, answer: bytearray) -> None:
        self._write(request, answer, no_stop=False)

    def _cmd_94(self, request: bytes, answer: bytearray) -> None:
        self._write(request, answer, no_stop=True)

    def _read(self, request: bytes, answer: bytearray) -> None:
        length = request[1] | request[2] << 8
        address = request[3] >> 1
        assert request[3] & 1, "read commands carry the read bit"
        answer[1] = 0x00
        self.read_nack = address != 0x48
        self.read_data = (
            b"" if self.read_nack else bytes(self.memory[self.pointer : self.pointer + length])
        )
        self.state = 0x00

    def _cmd_91(self, request: bytes, answer: bytearray) -> None:
        self._read(request, answer)

    def _cmd_93(self, request: bytes, answer: bytearray) -> None:
        self._read(request, answer)

    # Get I2C data
    def _cmd_40(self, request: bytes, answer: bytearray) -> None:
        if self.read_nack:
            answer[1] = 0x00
            answer[2] = 0x25
            return
        chunk, self.read_data = self.read_data[:60], self.read_data[60:]
        answer[1] = 0x00
        answer[2] = 0x55 if not self.read_data else 0x54
        answer[3] = len(chunk)
        answer[4 : 4 + len(chunk)] = chunk

    # GPIO
    def _cmd_50(self, request: bytes, answer: bytearray) -> None:
        for pin, setting in enumerate(self.gp_settings):
            if setting & 0x07:
                answer[2 + 2 * pin] = answer[3 + 2 * pin] = 0xEE
            else:
                answer[2 + 2 * pin] = (setting >> 4) & 1
                answer[3 + 2 * pin] = (setting >> 3) & 1

    def _cmd_51(self, request: bytes, answer: bytearray) -> None:
        for pin in range(4):
            offset = 2 + 4 * pin
            if self.gp_settings[pin] & 0x07:
                if request[offset] or request[offset + 2]:
                    answer[offset] = 0xEE
                continue
            if request[offset]:
                self.gp_settings[pin] = (self.gp_settings[pin] & ~0x10) | (
                    0x10 if request[offset + 1] else 0
                )
            if request[offset + 2]:
                self.gp_settings[pin] = (self.gp_settings[pin] & ~0x08) | (
                    0x08 if request[offset + 3] else 0
                )

    def _cmd_60(self, request: bytes, answer: bytearray) -> None:
        if request[7] & 0x80:
            # Writing the GP designation resets the outputs (datasheet note)
            self.gp_settings = [s & ~0x10 for s in request[8:12]]

    def _cmd_61(self, request: bytes, answer: bytearray) -> None:
        answer[22:26] = bytes(self.gp_settings)


@pytest.fixture
def chip(fake_hidapi):
    simulation = SimulatedMCP2221()
    fake_hidapi.plug(
        fake_hidapi.Hardware(0x04D8, 0x00DD, product="MCP2221 USB-I2C/UART Combo",
                             on_write=simulation.on_write)
    )
    return simulation


@pytest.fixture
def mcp(chip):
    bridge = MCP2221()
    yield bridge
    bridge.close()
    bridge.close_bridge()


# ┌─────┐
# │ I2C │
# └─────┘


def test_write_then_read_register(chip, mcp):
    sensor = I2C(mcp, 0x48)
    sensor.write(b"\x10\xca\xfe")
    assert chip.memory[0x10:0x12] == b"\xca\xfe"
    assert sensor.transfer(b"\x10", read_length=2) == b"\xca\xfe"
    # write no stop, then read with a repeated start
    assert 0x94 in chip.commands and 0x93 in chip.commands


def test_plain_read(chip, mcp):
    chip.memory[0:3] = b"abc"
    assert I2C(mcp, 0x48).transfer(read_length=3) == b"abc"
    assert 0x91 in chip.commands


def test_speed_applied_once(chip, mcp):
    sensor = I2C(mcp, 0x48)
    sensor.write(b"\x00")
    sensor.write(b"\x00")
    assert chip.divider == 12_000_000 // 100_000 - 3
    assert chip.commands.count(0x10) >= 1
    mcp.set_i2c_speed(400_000)
    assert chip.divider == 12_000_000 // 400_000 - 3
    assert mcp.i2c_speed == 400_000


def test_long_transfers_are_chunked(chip, mcp):
    sensor = I2C(mcp, 0x48)
    data = bytes(range(150))
    sensor.write(b"\x00" + data)
    assert chip.commands.count(0x90) == 3  # 151 bytes : 60 + 60 + 31
    assert sensor.transfer(b"\x00", read_length=150) == data


def test_nack(chip, mcp):
    with pytest.raises(AdapterWriteError, match="not acknowledged"):
        I2C(mcp, NACK_ADDRESS).write(b"\x00")
    # the bus was cancelled, the next transfer works
    assert I2C(mcp, 0x48).transfer(b"\x00", read_length=1) == b"\x00"


def test_nack_on_read(chip, mcp):
    with pytest.raises(AdapterWriteError, match="not acknowledged"):
        I2C(mcp, NACK_ADDRESS).transfer(read_length=2)


def test_several_devices_share_the_bridge(chip, mcp):
    first, second = I2C(mcp, 0x48), I2C(mcp, 0x48)
    errors = []

    def hammer(device, register):
        try:
            for value in range(20):
                device.write(bytes([register, value]))
                assert device.transfer(bytes([register]), read_length=1) == bytes([value])
        except Exception as e:  # pragma: no cover - reported below
            errors.append(e)

    threads = [
        threading.Thread(target=hammer, args=(first, 0x20)),
        threading.Thread(target=hammer, args=(second, 0x30)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors


def test_descriptor_names_the_bridge(chip, mcp):
    # MCP2221, or MCP2221#2... while the bridges of other tests are still alive
    assert re.fullmatch(r"i2c:MCP2221(#\d+)?@0x48", str(I2C(mcp, 0x48).descriptor))


def test_async_i2c(chip, mcp):
    async def main():
        sensor = AsyncI2C(mcp, 0x48)
        await sensor.write(b"\x05\x42")
        return await sensor.transfer(b"\x05", read_length=1)

    assert asyncio.run(main()) == b"\x42"


# ┌──────┐
# │ GPIO │
# └──────┘


def test_gpio_output(chip, mcp):
    mcp.configure_gpio(0, output=True, value=True)
    assert chip.gp_settings[0] & 0x07 == 0  # GPIO
    assert not chip.gp_settings[0] & 0x08  # output
    assert mcp.get_gpio(0) is True
    mcp.set_gpio(0, False)
    assert mcp.get_gpio(0) is False


def test_gpio_input(chip, mcp):
    mcp.configure_gpio(2, output=False)
    assert chip.gp_settings[2] & 0x08
    chip.gp_settings[2] |= 0x10  # the pin is driven high from outside
    assert mcp.get_gpio(2) is True


def test_gpio_not_configured(chip, mcp):
    assert mcp.get_gpios() == [None, None, None, None]
    with pytest.raises(AdapterConfigurationError, match="configure_gpio"):
        mcp.get_gpio(1)
    with pytest.raises(AdapterConfigurationError, match="configure_gpio"):
        mcp.set_gpio(1, True)


def test_configure_keeps_other_pins(chip, mcp):
    mcp.configure_gpio(0, output=True)
    mcp.configure_gpio(3, output=False)
    assert chip.gp_settings[1] == 0x01 and chip.gp_settings[2] == 0x01
    assert chip.gp_settings[0] & 0x07 == 0 and chip.gp_settings[3] & 0x07 == 0


@pytest.mark.parametrize("pin", [-1, 4])
def test_invalid_pin(chip, mcp, pin):
    with pytest.raises(AdapterConfigurationError):
        mcp.set_gpio(pin, True)


# ┌───────┐
# │ Other │
# └───────┘


def test_test_and_speed_checks(chip, mcp):
    assert mcp.test()
    with pytest.raises(AdapterConfigurationError):
        MCP2221(i2c_speed=1_000_000)


def test_name_keyword(chip):
    left = MCP2221(name="left")
    assert str(I2C(left, 0x48).descriptor) == "i2c:left@0x48"
    left.close_bridge()
