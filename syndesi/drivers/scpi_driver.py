# scpi_driver.py
# Sébastien Deriaz
# 27.04.2023
"""
Driver subclass for SCPI instruments that provides common functions like *IDN, *RST, *CLS, etc...
"""
from abc import abstractmethod

from ..adapters.bytesadapter import BytesAdapter
from ..protocols.scpi import SCPI
from .driver import Driver


class SCPIDriver(Driver):
    """
    SCPI Driver

    Parameters
    ----------
    adapter : BytesAdapter
    termination : str
        '\\n' by default
    """
    def __init__(self, adapter : BytesAdapter, termination : str = '\n') -> None:
        super().__init__()

        self._prot = SCPI(adapter, termination=termination)

    # Standard SCPI commands
    def get_identification(self) -> str:
        """
        Return identification returned by '*IDN?'

        Returns
        -------
        identification : str
        """
        return self._prot.query('*IDN?')

    def get_system_error(self) -> str:
        """
        Return the last error issued by the instrument

        Returns
        -------
        error : str
        """
        return self._prot.query('SYST:ERR?')

    def get_system_version(self) -> str:
        """
        Get the software version of the equipment

        Returns
        -------
        version : str
        """
        return self._prot.query('SYST:VERS?')

    def clear_status_registers(self) -> None:
        """
        Clear event registers as well as error queue
        """
        self._prot.write('*CLS')

    def trigger(self) -> None:
        """
        Trigger
        """
        self._prot.write('*TRG')

    def reset(self) -> None:
        """
        Reset the instrument to factory state
        """
        self._prot.write('*RST')

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
