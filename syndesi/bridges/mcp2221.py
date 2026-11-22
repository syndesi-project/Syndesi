# File : mcp2221.py
# Author : Sébastien Deriaz
# License : GPL
"""
MCP2221 / MCP2221A, Microchip USB to I2C and GPIO converter, as a bridge

The chip is a HID device : every command is a 64 bytes output report, answered by a
64 bytes input report whose first byte repeats the command. This driver sends them with
HID.query(), on the bridge thread, so it can wait for the answers without ever blocking
the reactor

    mcp = MCP2221()                         # the first MCP2221 connected
    sensor = I2C(mcp, 0x48)                 # an I2C device behind it
    sensor.transfer(b"\\x00", read_length=2)

    mcp.configure_gpio(0, output=True)      # GP0 as an output
    mcp.set_gpio(0, True)

The UART of the chip is a separate USB CDC interface : open it as an ordinary
SerialPort (/dev/ttyACM0, COM5, ...)

The command codes and the status bytes come from the MCP2221A datasheet (DS20005565),
the sequencing (retries, cancel, NACK detection) from the drivers proven on the chip,
such as Adafruit Blinka
"""

from __future__ import annotations

import time

from ..adapters.hid import HID
from ..drivers.driver import Driver
from ..tools.errors import (
    AdapterConfigurationError,
    AdapterReadError,
    AdapterWriteError,
)
from .bridge import I2CBridge

VENDOR_ID = 0x04D8
PRODUCT_ID = 0x00DD
REPORT_SIZE = 64

# ┌──────────┐
# │ Commands │
# └──────────┘

_STATUS = 0x10
_I2C_WRITE = 0x90
_I2C_WRITE_REPEATED_START = 0x92
_I2C_WRITE_NO_STOP = 0x94
_I2C_READ = 0x91
_I2C_READ_REPEATED_START = 0x93
_I2C_GET_DATA = 0x40
_GET_GPIO = 0x50
_SET_GPIO = 0x51
_SET_SRAM = 0x60
_GET_SRAM = 0x61
_RESET = 0x70

# Status / set parameters, request
_CANCEL_TRANSFER = 0x10
_SET_SPEED = 0x20
# Status / set parameters, answer
_SPEED_SET = 0x20
_STATUS_STATE = 8          # state of the I2C engine
_STATUS_FLAGS = 20         # bit 6 : the address was not acknowledged
_ADDRESS_NACK_FLAG = 0x40

# I2C engine states
_STATE_IDLE = 0x00
_STATE_START_TIMEOUT = 0x12
_STATE_WRITE_ADDRESS_TIMEOUT = 0x23
_STATE_ADDRESS_NACK = 0x25
_STATE_PARTIAL_DATA = 0x41
_STATE_WRITE_DATA_TIMEOUT = 0x44
_STATE_WRITING_NO_STOP = 0x45
_STATE_STOP_TIMEOUT = 0x62
_FATAL_STATES = {
    _STATE_START_TIMEOUT: "start timeout, is the bus pulled up?",
    _STATE_WRITE_ADDRESS_TIMEOUT: "address timeout",
    _STATE_ADDRESS_NACK: "address not acknowledged",
    _STATE_WRITE_DATA_TIMEOUT: "data timeout",
    _STATE_STOP_TIMEOUT: "stop timeout",
}

# Get I2C data, answer
_READ_COMPLETE = 0x55
_READ_PARTIAL = 0x54
_READ_ERROR = 0x7F

# GPIO
_GPIO_COUNT = 4
_NOT_A_GPIO = 0xEE
_DIRECTION_OUTPUT = 0x00
_DIRECTION_INPUT = 0x01
# SRAM : GP designation, alter flag and settings bits
_ALTER_GP_DESIGNATION = 0x80
_SRAM_GP_SETTINGS = 22     # GP0..GP3 settings in the get SRAM answer
_GP_FUNCTION_MASK = 0x07   # 0 : GPIO
_GP_INPUT_BIT = 0x08
_GP_VALUE_BIT = 0x10

_OK = 0x00
_MAX_I2C_CHUNK = 60
_MAX_I2C_LENGTH = 0xFFFF
_RETRIES = 50
_RETRY_DELAY = 0.001
_CLOCK = 12_000_000


class MCP2221(Driver, I2CBridge):
    """
    Microchip MCP2221 / MCP2221A : an I2C bus and four GPIOs over USB

    Parameters
    ----------
    adapter : HID or None
        HID adapter of the chip, the first MCP2221 connected if None
    serial_number : str or None
        To choose between several chips, when adapter is None. The serial number has
        to be enabled in the chip's flash, it is off from the factory
    i2c_speed : int
        I2C clock in Hz, 50 kHz to 400 kHz, 100 kHz by default
    """

    VENDOR_ID = VENDOR_ID
    PRODUCT_ID = PRODUCT_ID

    def __init__(
        self,
        adapter: HID | None = None,
        *,
        serial_number: str | None = None,
        i2c_speed: int = 100_000,
    ) -> None:
        super().__init__()
        self._check_speed(i2c_speed)
        self.hid = (
            adapter
            if adapter is not None
            else HID(
                VENDOR_ID,
                PRODUCT_ID,
                serial_number=serial_number,
                report_size=REPORT_SIZE,
            )
        )
        self._i2c_speed = i2c_speed
        self._speed_applied = False

    # ┌────────┐
    # │ Driver │
    # └────────┘

    def open(self) -> None:
        self.hid.open()

    def close(self) -> None:
        self.hid.close()
        self._speed_applied = False

    def test(self) -> bool:
        try:
            self.run(self._command, bytes([_STATUS])).result()
        except (AdapterReadError, AdapterWriteError):
            return False
        return True

    # ┌─────┐
    # │ I2C │
    # └─────┘

    @property
    def i2c_speed(self) -> int:
        """I2C clock, in Hz"""
        return self._i2c_speed

    def set_i2c_speed(self, speed: int) -> None:
        """
        Set the I2C clock

        Parameters
        ----------
        speed : int
            Hz, 50 kHz to 400 kHz
        """
        self._check_speed(speed)
        self.run(self._set_speed, speed).result()

    def i2c_transfer(self, address: int, data: bytes, read_length: int) -> bytes:
        if read_length > _MAX_I2C_LENGTH or len(data) > _MAX_I2C_LENGTH:
            raise AdapterWriteError(
                f"{self} : an I2C transfer is {_MAX_I2C_LENGTH} bytes at most"
            )
        if not self._speed_applied:
            self._set_speed(self._i2c_speed)
        try:
            if read_length == 0:
                self._i2c_write(_I2C_WRITE, address, data)
                return b""
            if not data:
                return self._i2c_read(_I2C_READ, address, read_length)
            self._i2c_write(_I2C_WRITE_NO_STOP, address, data)
            return self._i2c_read(_I2C_READ_REPEATED_START, address, read_length)
        except (AdapterWriteError, AdapterReadError):
            # Leave the bus idle for the next transfer
            self._cancel()
            raise

    # ┌──────┐
    # │ GPIO │
    # └──────┘

    def configure_gpio(self, pin: int, output: bool, value: bool = False) -> None:
        """
        Make a pin a GPIO, as an input or an output

        The configuration lasts until the chip is reset or unplugged

        Parameters
        ----------
        pin : int
            0 to 3 (GP0 to GP3)
        output : bool
            True for an output, False for an input
        value : bool
            Level of an output
        """
        self._check_pin(pin)
        self.run(self._configure_gpio, pin, output, value).result()

    def set_gpio(self, pin: int, value: bool) -> None:
        """
        Set the level of an output

        Parameters
        ----------
        pin : int
            0 to 3 (GP0 to GP3)
        value : bool
        """
        self._check_pin(pin)
        self.run(self._set_gpio, pin, value, None).result()

    def get_gpio(self, pin: int) -> bool:
        """
        Level of a GPIO, input or output

        Parameters
        ----------
        pin : int
            0 to 3 (GP0 to GP3)
        """
        self._check_pin(pin)
        value = self.run(self._get_gpios).result()[pin]
        if value is None:
            raise AdapterConfigurationError(
                f"{self} : GP{pin} isn't a GPIO, call configure_gpio({pin}, ...) first"
            )
        return value

    def get_gpios(self) -> list[bool | None]:
        """Level of GP0 to GP3, None for a pin that isn't a GPIO"""
        return self.run(self._get_gpios).result()

    # ┌───────┐
    # │ Other │
    # └───────┘

    def reset(self) -> None:
        """
        Reset the chip. It leaves the USB bus and comes back, the HID adapter is closed
        """
        self.run(self._reset).result()

    # ┌──────────────────────────┐
    # │ Bridge thread, internals │
    # └──────────────────────────┘

    def _command(self, request: bytes) -> bytes:
        """Send one command report and return the report that answers it"""
        answer = self.hid.query(request.ljust(REPORT_SIZE, b"\x00"))
        if len(answer) < 2 or answer[0] != request[0]:
            raise AdapterReadError(
                f"{self} : unexpected answer {answer[:4].hex()}... "
                f"to command {request[0]:#04x}"
            )
        return answer

    def _status(self) -> bytes:
        return self._command(bytes([_STATUS]))

    def _cancel(self) -> None:
        try:
            self._command(bytes([_STATUS, 0x00, _CANCEL_TRANSFER]))
        except (AdapterReadError, AdapterWriteError):
            pass  # best effort, the transfer error is the one that matters

    def _set_speed(self, speed: int) -> None:
        if self._status()[_STATUS_STATE] != _STATE_IDLE:
            self._cancel()
        answer = self._command(
            bytes([_STATUS, 0x00, 0x00, _SET_SPEED, _CLOCK // speed - 3])
        )
        if answer[3] != _SPEED_SET:
            raise AdapterWriteError(f"{self} : cannot set the I2C speed, the bus is busy")
        self._i2c_speed = speed
        self._speed_applied = True

    def _i2c_write(self, command: int, address: int, data: bytes) -> None:
        if self._status()[_STATUS_STATE] != _STATE_IDLE:
            self._cancel()
        length = len(data)
        header = bytes([command, length & 0xFF, length >> 8, address << 1])
        position = 0
        retries = 0
        # An empty write still sends one report : the address alone, to probe
        while True:
            chunk = data[position : position + _MAX_I2C_CHUNK]
            answer = self._command(header + chunk)
            if answer[1] != _OK:
                self._raise_if_fatal(address, answer[2])
                retries += 1
                if retries >= _RETRIES:
                    raise AdapterWriteError(f"{self} : I2C write to {address:#04x}, busy")
                time.sleep(_RETRY_DELAY)
                continue
            retries = 0
            while self._status()[_STATUS_STATE] == _STATE_PARTIAL_DATA:
                time.sleep(_RETRY_DELAY)
            position += len(chunk)
            if position >= length:
                break
        self._wait_write_done(command, address)

    def _wait_write_done(self, command: int, address: int) -> None:
        for _ in range(_RETRIES):
            status = self._status()
            if status[_STATUS_FLAGS] & _ADDRESS_NACK_FLAG:
                raise AdapterWriteError(
                    f"I2C transfer to {address:#04x} on {self} failed : address not "
                    "acknowledged"
                )
            state = status[_STATUS_STATE]
            if state == _STATE_IDLE:
                return
            if state == _STATE_WRITING_NO_STOP and command == _I2C_WRITE_NO_STOP:
                return
            self._raise_if_fatal(address, state)
            time.sleep(_RETRY_DELAY)
        raise AdapterWriteError(f"I2C transfer to {address:#04x} on {self} : no end")

    def _i2c_read(self, command: int, address: int, length: int) -> bytes:
        state = self._status()[_STATUS_STATE]
        if state not in (_STATE_IDLE, _STATE_WRITING_NO_STOP):
            self._cancel()
        answer = self._command(
            bytes([command, length & 0xFF, length >> 8, (address << 1) | 1])
        )
        if answer[1] != _OK:
            raise AdapterReadError(
                f"I2C read from {address:#04x} on {self} refused (state {answer[2]:#04x})"
            )
        received = b""
        while len(received) < length:
            received += self._get_data(address, length - len(received))
        return received

    def _get_data(self, address: int, remaining: int) -> bytes:
        """One get I2C data command, retried while the chip has nothing yet"""
        for _ in range(_RETRIES):
            answer = self._command(bytes([_I2C_GET_DATA]))
            if answer[1] == _STATE_PARTIAL_DATA:
                time.sleep(_RETRY_DELAY)
                continue
            if answer[2] == _STATE_ADDRESS_NACK:
                # The same error as a NACK on a write, like the other I2C bridges
                raise AdapterWriteError(
                    f"I2C transfer to {address:#04x} on {self} failed : address not "
                    "acknowledged"
                )
            if answer[1] != _OK:
                raise AdapterReadError(f"I2C read from {address:#04x} on {self} failed")
            if answer[3] == _READ_ERROR:
                time.sleep(_RETRY_DELAY)
                continue
            count = min(answer[3], _MAX_I2C_CHUNK, remaining)
            if count == 0:
                time.sleep(_RETRY_DELAY)
                continue
            return bytes(answer[4 : 4 + count])
        raise AdapterReadError(f"I2C read from {address:#04x} on {self} : no data")

    def _raise_if_fatal(self, address: int, state: int) -> None:
        reason = _FATAL_STATES.get(state)
        if reason is not None:
            raise AdapterWriteError(
                f"I2C transfer to {address:#04x} on {self} failed : {reason}"
            )

    def _configure_gpio(self, pin: int, output: bool, value: bool) -> None:
        settings = list(self._command(bytes([_GET_SRAM]))[
            _SRAM_GP_SETTINGS : _SRAM_GP_SETTINGS + _GPIO_COUNT
        ])
        setting = settings[pin] & ~(_GP_FUNCTION_MASK | _GP_INPUT_BIT | _GP_VALUE_BIT)
        if not output:
            setting |= _GP_INPUT_BIT
        if value:
            setting |= _GP_VALUE_BIT
        settings[pin] = setting
        # Bytes 2 to 6 alter nothing (clock, DAC, ADC, interrupt), byte 7 the GP pins
        request = bytes([_SET_SRAM, 0x00, 0, 0, 0, 0, 0, _ALTER_GP_DESIGNATION])
        answer = self._command(request + bytes(settings))
        if answer[1] != _OK:
            raise AdapterWriteError(f"{self} : cannot configure GP{pin}")
        # Writing the SRAM resets the GPIO outputs, set them again
        self._set_gpio(pin, value, output)

    def _set_gpio(self, pin: int, value: bool, output: bool | None) -> None:
        request = bytearray(2 + 4 * _GPIO_COUNT)
        request[0] = _SET_GPIO
        offset = 2 + 4 * pin
        request[offset] = 1                      # alter the output value
        request[offset + 1] = 1 if value else 0
        if output is not None:
            request[offset + 2] = 1              # alter the direction
            request[offset + 3] = _DIRECTION_OUTPUT if output else _DIRECTION_INPUT
        answer = self._command(bytes(request))
        if answer[1] != _OK or answer[offset] == _NOT_A_GPIO:
            raise AdapterConfigurationError(
                f"{self} : GP{pin} isn't a GPIO, call configure_gpio({pin}, ...) first"
            )

    def _get_gpios(self) -> list[bool | None]:
        answer = self._command(bytes([_GET_GPIO]))
        values: list[bool | None] = []
        for pin in range(_GPIO_COUNT):
            value = answer[2 + 2 * pin]
            values.append(None if value == _NOT_A_GPIO else bool(value))
        return values

    def _reset(self) -> None:
        # The chip resets right away, without answering
        self.hid.write(bytes([_RESET, 0xAB, 0xCD, 0xEF]).ljust(REPORT_SIZE, b"\x00"))
        self._speed_applied = False

    # ┌────────┐
    # │ Checks │
    # └────────┘

    @staticmethod
    def _check_speed(speed: int) -> None:
        if not 50_000 <= speed <= 400_000:
            raise AdapterConfigurationError(
                f"Invalid I2C speed : {speed} Hz, expected 50 kHz to 400 kHz"
            )

    @staticmethod
    def _check_pin(pin: int) -> None:
        if not 0 <= pin < _GPIO_COUNT:
            raise AdapterConfigurationError(f"Invalid GPIO : {pin}, expected 0 to 3")

    def __repr__(self) -> str:
        return f"MCP2221({self.hid.descriptor})"
