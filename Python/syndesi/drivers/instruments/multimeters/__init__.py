from abc import ABC, abstractmethod

class IVoltmeter(ABC):
    # Provides a voltage measurement
    @abstractmethod
    def measure_dc_voltage(self) -> float:
        pass
    
    @abstractmethod
    def measure_ac_voltage(self) -> float:
        pass

class IAmmeter(ABC):
    # Provides a current measurement
    @abstractmethod
    def measure_dc_current(self) -> float:
        pass
    
    @abstractmethod
    def measure_ac_current(self) -> float:
        pass

class IOhmMeter(ABC):
    # Provides a resistance measurement
    @abstractmethod
    def measure_resistance(self) -> float:
        """
        2-wire measurement is implied
        """
        pass

# Multimeter combines Voltmeter, Ammeter and OhmMeter
class IMultimeter(IVoltmeter, IAmmeter, IOhmMeter):
    pass