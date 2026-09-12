# File : backend.py
# Author : Sébastien Deriaz
# License : GPL
"""
Backends, the layer that talks to the hardware

A backend does one syscall at a time and knows nothing about threads, framing or
the reactor. Its only link to the outside is selectable(), which returns the file
descriptor to watch. A backend that cannot be polled (VISA, serial on Windows)
runs its own reader thread and exposes a socketpair here instead
"""

import math
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Generic, TypeVar

from syndesi.adapters.stop_conditions import StopCondition
from syndesi.adapters.utils import Fragment, HasFileno
from syndesi.tools.errors import SyndesiError


@dataclass(kw_only=True)
class SyndesiEvent:
    """Generic event, used to move information asynchronously from the adapter worker thread"""
    timestamp : float = float("nan")

    def __post_init__(self) -> None:
        if math.isnan(self.timestamp):
            self.timestamp = time.time()

class Descriptor(ABC):
    """
    Descriptor base class. A descriptor is a string to define the main parameters
    of an adapter (ip address, port, baudrate, etc...)
    """

    DETECTION_PATTERN = ""

    def __init__(self) -> None:
        return None

    @staticmethod
    @abstractmethod
    def from_string(string: str) -> "Descriptor":
        """
        Create a Descriptor class from a string
        """

    @abstractmethod
    def is_initialized(self) -> bool:
        """Return True if the descriptor is initialized"""

DescriptorT = TypeVar("DescriptorT", bound=Descriptor)
BackendDataT = TypeVar("BackendDataT")

class BackendError(SyndesiError):
    """Base class for every backend error. The engine turns these into adapter errors"""

class BackendDisconnectedError(BackendError):
    """The target closed the connection"""

class BackendOpenError(BackendError):
    """The backend could not be opened"""

class BackendWriteError(BackendError):
    """The backend could not write, or could not write everything"""

class BackendReadError(BackendError):
    """The backend could not read"""

class AdapterBackend(Generic[DescriptorT, BackendDataT], ABC):
    """
    Backend base class, one per media type

    Parameters
    ----------
    descriptor : Descriptor
    """

    descriptor : DescriptorT

    def __init__(self, descriptor : DescriptorT) -> None:
        super().__init__()
        self.descriptor = descriptor

    @abstractmethod
    def selectable(self) -> HasFileno | None:
        """
        Return an object with a fileno to listen on for incoming data

        None when there is nothing to watch, which is the case before open and
        after close
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
        """Timeout used when the user doesn't set one"""

    @property
    @abstractmethod
    def default_stop_conditions(self) -> list[StopCondition]:
        """Stop-conditions used when the user doesn't set any"""
