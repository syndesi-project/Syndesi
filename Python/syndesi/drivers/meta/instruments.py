# Instruments meta classes
from abc import ABC, abstractmethod
from .base import Device


class SPCIDevice(Device):
    def getIdentifier(self) -> str:
        """
        Query the manufacturer, product type, serial number as well as hardware and/or software versions.
        """
        # TODO : Fix how the wrapper is used, timeout maybe ?
        self._wrapper.write('*IDN?\n')
        idn : bytearray = self._wrapper.read()

        return idn.decode('ASCII', errors='replace')

    def getErrorCode(self) -> tuple:
        """
        Query the system's error code
        """
        self._wrapper.write('SYST:ERR?\n')
        output : str = self._wrapper.read()
        try:
            code, desc = output.split(' ', 1)
        except ValueError:
            code, desc = None, None
        return code, desc

    def getVersion(self) -> str:
        """
        Query the version of the equipment
        """
        self._wrapper.write('SYST:VER?\n')
        output = self._wrapper.read()
        return output

class Voltmeter(Device, ABC):
    # Provides a voltage measurement
    @abstractmethod
    def measureDC(self) -> float:
        pass

    def measureAC(self) -> float:
        pass


class Ammeter(Device):
    # Provides a current measurement
    def measureDC(self) -> float:
        pass
    
    def measureAC(self) -> float:
        pass

class PowersupplyDC(Device):
    # Provides power supply functions (one channel only)
    def setVoltage(self, volts : float):
        pass

    def getVoltage(self) -> float:
        pass

    def setCurrent(self, amps : float):
        pass

    def getCurrent(self) -> float:
        pass

    def setOutputState(self, state : bool):
        pass

    def measureVoltage(self) -> float:
        pass

    def measureCurrent(self) -> float:
        pass

class MultiChannelPowersupplyDC(Device):
    # Provides power supply functions (multi channel)
    def setVoltage(self, Channel : int, volts : float):
        pass

    def getVoltage(self, channel : int) -> float:
        pass

    def setCurrent(self, channel : int, amps : float):
        pass

    def getCurrent(self, channel : int) -> float:
        pass

    def setOutputState(self, channel : int, state : bool):
        pass

    def measureCurrent(self, channel) -> float:
        pass

    def measureVoltage(self, channel) -> float:
        pass