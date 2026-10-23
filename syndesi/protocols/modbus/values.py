# File : values.py
# Author : Sébastien Deriaz
# License : GPL
"""
Values spread over several Modbus registers (integers, floats, strings)
"""

from __future__ import annotations

import struct
from typing import cast

from .common import (
    Endian,
)

DEFAULT_ENCODING = "utf-8"
DEFAULT_PADDING = "\0"

# byte_order vs word_order
#
# byte_order : Order by the individual bytes inside a modbus register
# word_order : Order of the different registers to constitute a multi-register value
#
# Example : Integer 0x12345678 (A=0x12 B=0x34 C=56 D=78)
#
# | byte_order | word_order | Result |
# | -----------|------------|--------|
# | 'big'      | 'big'      | ABCD   |
# | 'little'   | 'big'      | BADC   |
# | 'big'      | 'little'   | CDAB   |
# | 'little'   | 'little'   | DCBA   |


class ModbusMultiRegisterValue:
    _buffer: bytes

    # ENDIAN_SYMBOL = {Endian.BIG: ">", Endian.LITTLE: "<"}
    # Formats based on the number of registers (half the number of bytes)
    INT_FORMAT = {
        1: "h",
        2: "i",
        4: "q",
    }
    UINT_FORMAT = {
        1: "H",
        2: "I",  # or 'L'
        4: "Q",
    }
    FLOAT_FORMAT = {2: "f", 4: "d"}

    def __init__(
        self,
        buffer: bytes,
        *,
        word_order: Endian | str,
        byte_order: Endian | str,
    ) -> None:
        self._word_order = Endian(word_order)
        self._byte_order = Endian(byte_order)

        self._buffer = buffer

    @staticmethod
    def from_registers(
        register_values: list[int], byte_order: Endian | str, word_order: Endian | str
    ) -> ModbusMultiRegisterValue:
        direction = 1 if Endian(word_order) == Endian.BIG else -1
        buffer = b"".join(
            [
                x.to_bytes(2, byteorder=Endian(byte_order).value)
                for x in register_values[::direction]
            ]
        )
        return ModbusMultiRegisterValue(
            buffer, word_order=word_order, byte_order=byte_order
        )

    def to_registers(self) -> list[int]:
        direction = 1 if self._word_order == Endian.BIG else -1
        registers = [
            int.from_bytes(
                self._buffer[2 * i : 2 * i + 2], byteorder=self._byte_order.value
            )
            for i in range(len(self._buffer) // 2)
        ]
        return registers[::direction]

    def to_int(self) -> int:
        n = len(self._buffer) // 2
        try:
            fmt = self.INT_FORMAT[n]
        except KeyError as e:
            raise ValueError(f"Buffer of size {n} cannot be converted to int") from e

        output = cast(int, struct.unpack(f">{fmt}", self._buffer)[0])

        return output

    def to_uint(self) -> int:
        n = len(self._buffer) // 2
        try:
            fmt = self.UINT_FORMAT[n]
        except KeyError as e:
            raise ValueError(f"Buffer of size {n} cannot be converted to uint") from e

        output = cast(int, struct.unpack(f">{fmt}", self._buffer)[0])
        return output

    def to_float(self) -> float:
        n = len(self._buffer) // 2
        try:
            fmt = self.FLOAT_FORMAT[n]
        except KeyError as e:
            raise ValueError(f"Buffer of size {n} cannot be converted to float") from e

        output = cast(int, struct.unpack(f">{fmt}", self._buffer)[0])
        return output

    def to_string(
        self, encoding: str = DEFAULT_ENCODING, padding: str = DEFAULT_PADDING
    ) -> str:
        data = self.to_array()
        # Cast
        decoded_data = data.decode(encoding)
        return decoded_data.strip(padding)

    def to_array(self) -> bytes:
        return self._buffer

    @staticmethod
    def from_int(
        value: int,
        n_registers: int,
        word_order: Endian | str = Endian.BIG,
        byte_order: Endian | str = Endian.BIG,
    ) -> ModbusMultiRegisterValue:
        return ModbusMultiRegisterValue(
            struct.pack(">" + ModbusMultiRegisterValue.INT_FORMAT[n_registers], value),
            word_order=word_order,
            byte_order=byte_order,
        )

    @staticmethod
    def from_uint(
        value: int,
        n_registers: int,
        word_order: Endian | str = Endian.BIG,
        byte_order: Endian | str = Endian.BIG,
    ) -> ModbusMultiRegisterValue:
        return ModbusMultiRegisterValue(
            struct.pack(">" + ModbusMultiRegisterValue.UINT_FORMAT[n_registers], value),
            word_order=word_order,
            byte_order=byte_order,
        )

    @staticmethod
    def from_float(
        value: float,
        n_registers: int,
        word_order: Endian | str = Endian.BIG,
        byte_order: Endian | str = Endian.BIG,
    ) -> ModbusMultiRegisterValue:
        return ModbusMultiRegisterValue(
            struct.pack(
                ">" + ModbusMultiRegisterValue.FLOAT_FORMAT[n_registers], value
            ),
            word_order=word_order,
            byte_order=byte_order,
        )

    @staticmethod
    def from_string(
        value: str,
        n_registers: int,
        padding: str = DEFAULT_PADDING,
        encoding: str = DEFAULT_ENCODING,
        word_order: Endian | str = Endian.BIG,
        byte_order: Endian | str = Endian.BIG,
    ) -> ModbusMultiRegisterValue:
        buffer = value.encode(encoding)
        buffer_size = n_registers * 2
        if len(buffer) > buffer_size:
            raise ValueError(
                f"String '{value}' cannot fit in {n_registers} registers ({buffer_size} bytes)"
            )

        padding_bytes = padding.encode(encoding)
        buffer += padding_bytes * (buffer_size - len(buffer))
        return ModbusMultiRegisterValue(
            buffer, word_order=word_order, byte_order=byte_order
        )

    @staticmethod
    def from_array(
        array: bytes,
        n_registers: int,
        word_order: Endian | str = Endian.BIG,
        byte_order: Endian | str = Endian.BIG,
    ) -> ModbusMultiRegisterValue:
        if len(array) != 2 * n_registers:
            raise ValueError(
                f"Cannot fit '{array!r}' ({len(array)}) into {n_registers} registers ({2*n_registers})"
            )
        return ModbusMultiRegisterValue(
            array, word_order=word_order, byte_order=byte_order
        )
