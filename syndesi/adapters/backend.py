# File : backend.py
# Author : Sébastien Deriaz
# License : GPL


from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from syndesi.adapters.stop_conditions import StopCondition
from syndesi.adapters.utils import Fragment, HasFileno
from syndesi.component import Descriptor
from syndesi.tools.errors import SyndesiError


DescriptorT = TypeVar("DescriptorT", bound=Descriptor)
BackendDataT = TypeVar("BackendDataT")

class BackendError(SyndesiError):
    ...

class BackendDisconnectedError(BackendError):
    ...

class BackendOpenError(BackendError):
    ...

class BackendWriteError(BackendError):
    ...

class BackendReadError(BackendError):
    ...


class AdapterBackend(Generic[DescriptorT, BackendDataT], ABC):
    descriptor : DescriptorT

    def __init__(self, descriptor : DescriptorT) -> None:
        super().__init__()
        self.descriptor = descriptor

    @abstractmethod
    def selectable(self) -> HasFileno:
        """
        Returns a fileno on which to listen
        for incoming data
        """

    @abstractmethod
    def open(self, timeout : float | None) -> None:
        """
        Backend open method
        
        Can raise :
        
            * BackendOpenError
        """

    @abstractmethod
    def close(self) -> None:
        """
        Backend close method        
        """

    @abstractmethod
    def read(self, fragment_timestamp : float) -> Fragment[BackendDataT]:
        """
        Backend read method

        Can raise :

        * BackendDisconnectedError
        * BackendReadError
        """

    @abstractmethod
    def write(self, data : BackendDataT) -> None:
        """
        Backend write method

        Can raise :

        * BackendWriteError
        """

    @property
    @abstractmethod
    def default_timeout(self) -> float | None:
        ...

    @property
    @abstractmethod
    def default_stop_conditions(self) -> list[StopCondition]:
        ...

