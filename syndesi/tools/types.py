# File : types.py
# Author : Sébastien Deriaz
# License : GPL
"""
Type tools
"""

from typing import Any


def to_bytes(data: str | bytes) -> bytes:
    """
    Convert data to bytes array
    bytearray -> bytearray
    bytes -> bytes
    str -> bytes (UTF-8 encoding by default)
    """
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    raise ValueError(f"Invalid data type : {type(data)}")
