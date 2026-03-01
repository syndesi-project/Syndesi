# File : utils.py
# Author : Sébastien Deriaz
# License : GPL
"""
Various utilities for adapters
"""

from typing import Protocol


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