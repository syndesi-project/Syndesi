# File : types.py
# Author : Sébastien Deriaz
# License : GPL

from typing import TYPE_CHECKING, Any, TypeGuard

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

if TYPE_CHECKING:
    import numpy as np_typing

    NumberLike = int | float | np_typing.number[Any]
else:
    NumberLike = int | float | np.number  # runtime will resolve string

def is_number(X: Any) -> TypeGuard[NumberLike]:
    """
    Check if the given X is an instance of int or float

    Parameters
    ----------
    X : any

    Returns
    -------
    result : bool
    """
    if np is None:
        return isinstance(X, int | float)
    else:
        return isinstance(X, int | float | np.number)


def assert_number(*args: Any) -> None:
    """
    Checks if the given argument(s) is a number.
    A TypeError is raised if it isn't the case

    Parameters
    ----------
    args
    """
    for arg in args:
        if not is_number(arg):
            raise TypeError(f"Variable {arg} should be a number")


def to_bytes(data: str | bytes) -> bytes:
    """
    Convert data to bytes array
    bytearray -> bytearray
    bytes -> bytes
    str -> bytes (UTF-8 encoding by default)
    """
    if isinstance(data, bytes):
        return data
    elif isinstance(data, str):
        return data.encode("utf-8")
    else:
        raise ValueError(f"Invalid data type : {type(data)}")
