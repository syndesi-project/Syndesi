# File : driver.py
# Author : Sébastien Deriaz
# License : GPL

from abc import abstractmethod
from typing import Generic, TypeVar

from ..shell.shell import shell_command

DataT = TypeVar("DataT")

class Driver(Generic[DataT]):
    """
    Driver base class. A Driver implements target-specific instructions
    over a given Protocol or Adapter. Drivers can also be composed to implement
    more complex features
    """

    def __init__(self) -> None:
        pass

    @shell_command()
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
    def write(self, data : DataT):
        """
        Write data to the target
        """

    @abstractmethod
    def read(self) -> DataT:
        """
        Read data from the target
        """

    def query(self, data : DataT) -> DataT:
        """
        Query data from the target
        """
        raise NotImplementedError()
