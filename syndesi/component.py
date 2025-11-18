# File : component.py
# Author : Sébastien Deriaz
# License : GPL
"""
Component is the base of the main syndesi classes : Adapters, Protocols and Drivers
"""

from abc import ABC, abstractmethod
import logging
from typing import TypeVar, Generic

from syndesi.tools.errors import AdapterFailedToOpen

from .tools.log_settings import LoggerAlias

T  = TypeVar("T")

class Component(ABC, Generic[T]):
    """Syndesi Component
    
    A Component is the elementary class of Syndesi. It is the base
    of all classes the user will be using
    """
    def __init__(self, logger_alias : LoggerAlias) -> None:
        super().__init__()
        self._logger = logging.getLogger(logger_alias.value)

    @abstractmethod
    def open(self) -> None:
        """
        Open communication with the device    
        """

    @abstractmethod
    def close(self) -> None:
        """
        Close communication with the device
        """

    def try_open(self) -> bool:
        """
        Try to open communication with the device
        Return True if sucessful and False otherwise

        Returns
        -------
        success : bool
        """
        try:
            self.open()
            return True
        except AdapterFailedToOpen:
            return False

    @abstractmethod
    def read(self) -> T:
        """
        Read data from the device
        
        Returns
        -------
        data : T
        """

    # @abstractmethod
    # def read_detailed(self) -> AdapterReadPayload:
    #     """
    #     Read from the device and return the full payload class (AdapterReadPayload)
    #     To read data only, use .read()
    #     """
    @abstractmethod
    def write(self, data: T) -> None:
        """
        Write data to the device

        Parameters
        ----------
        data : T
        """
