# Instruments meta classes

from abc import ABC, abstractmethod



class Voltmeter(ABC):
    # Provides a voltage measurement
    @abstractmethod
    def measureDC() -> Float:
        pass

    def measureAC() -> Float:
        pass


class Ammeter:
    # Provides a current measurement
    def measureDC() -> Float:
        pass
    
    def measureAC() -> Float:
        pass

class Powersupply:
    # Provides power supply functions (one channel only)
    def setVoltage(volts : Float):
        pass

    def getVoltage() -> Float:
        pass

    def setAmperage(amps : Float):
        pass

    def getAmperage() -> Float:
        pass
