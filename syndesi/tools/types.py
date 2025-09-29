# File : types.py
# Author : Sébastien Deriaz
# License : GPL

# try:
#     import numpy as np
#     HAS_NUMPY = True
# except ImportError:
#     HAS_NUMPY = False
# class _Default : __slots__ = ()
# DEFAULT : Final[_Default] = _Default()
# EllipsisType : TypeAlias = _Default
# def is_default(x : Any) -> TypeGuard[EllipsisType]:
#     return x is DEFAULT
# DEFAULT : EllipsisType = ...
# EllipsisType : TypeAlias = EllipsisType
# def is_default(x : Any) -> TypeGuard[EllipsisType]:
#     return x is DEFAULT
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

# def is_byte_instance(X : Any):
#     """
#     Check if the given X is an instance of bytearray or bytes

#     Parameters
#     ----------
#     X : any

#     Returns
#     -------
#     result : bool
#     """
#     result = isinstance(X, (bytearray, bytes))
#     return result


# def assert_byte_instance(*args):
#     """
#     Checks if the given argument(s) is of type bytes
#     or bytes. A TypeError is raised if it isn't the case

#     Parameters
#     ----------
#     args
#     """
#     for arg in args:
#         if not is_byte_instance(arg):
#             raise TypeError(f"Variable {arg} should be of type bytes or bytes")


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
