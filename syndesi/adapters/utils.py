# File : utils.py
# Author : Sébastien Deriaz
# License : GPL
"""
Various utilities for adapters
"""

from dataclasses import dataclass
from types import EllipsisType
from typing import Any, Generic, Protocol, TypeVar, cast


def nmin(a: float | None, b: float | None) -> float | None:
    """
    Return min of a and b, ignoring None values

    If both a and b are None, return None
    """
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


class HasFileno(Protocol):
    """
    A class to annotate objects that have a fileno function
    """

    def fileno(self) -> int:
        """
        Return file number
        """
        return -1


FragmentT = TypeVar("FragmentT")
SliceableFragmentT = TypeVar("SliceableFragmentT", bound="SupportsSlice")


class SupportsSlice(Protocol):
    """
    Data type supporting slice access.
    """

    def __getitem__(self, key: slice) -> Any: ...


@dataclass
class Fragment(Generic[FragmentT]):
    """
    Fragment class, holds a piece of data (generic) and the time at which it was received
    """

    data: FragmentT
    timestamp: float

    def __str__(self) -> str:
        return f"{self.data}@{self.timestamp}"

    def __repr__(self) -> str:
        return f"Fragment({self.data}@{self.timestamp})"

    def __getitem__(
        self: "Fragment[SliceableFragmentT]", key: slice
    ) -> "Fragment[SliceableFragmentT]":
        """
        Slice fragment data while preserving timestamp.
        """
        return Fragment(cast(SliceableFragmentT, self.data[key]), self.timestamp)


TimeoutType = EllipsisType | float | int | None
ValidTimeoutType = float | int | None