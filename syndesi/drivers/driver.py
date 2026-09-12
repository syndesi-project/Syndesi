# NOT YET PORTED to the backend/framer/engine/reactor architecture.
# This module still targets the removed Component/Adapter classes. It is kept
# as a reference while it gets ported, and excluded from the checkers until then
# mypy: ignore-errors
# pylint: skip-file
# ruff: noqa
# File : driver.py
# Author : Sébastien Deriaz
# License : GPL

"""
Driver and SubDriver classes

Drivers are bases classes for user implementation that implement
custom behaviour for a device / instrument / projet

SubDrivers do have have open/close/test methods as they are usually derived from a
Driver (like a single power supply channel). The main Driver is always responsible for
adapter/protocol management
"""

from abc import abstractmethod
from typing import ClassVar


class SubDriver:
    """
    A subdriver can be a single channel of an instrument, it doesn't need open/close/test but
    it is still a driver
    """
    CHANGELOG : ClassVar[dict[str, str]] = {}

class Driver(SubDriver):
    """
    Driver base class. A Driver implements target-specific instructions
    over a given Protocol or Adapter. Drivers can also be composed to implement
    more complex features
    """

    def __init__(self) -> None:
        pass

    @abstractmethod
    def open(self) -> None:
        """
        Open the driver and its protocols/adapters. Must be implemented
        by the user
        """

    @abstractmethod
    def close(self) -> None:
        """
        Close the driver and its protocols/adapters. Must be implemented
        by the user
        """

    @abstractmethod
    def test(self) -> bool:
        """
        Test communication with the target. Return True on success and False otherwise
        """
