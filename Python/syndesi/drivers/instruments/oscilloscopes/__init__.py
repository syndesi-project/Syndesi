from abc import ABC, abstractmethod
from enum import Enum

class IOscilloscope(ABC):
    class Coupling(Enum):
        DC = 0
        AC = 1
        GND = 2

    @abstractmethod
    def set_time_scale(self, seconds_per_div : float):
        pass

    @abstractmethod
    def set_voltage_scale(self, channel : int, volts_per_div : float):
        pass

    @abstractmethod
    def set_coupling(self, channel : int, coupling : Coupling):
        pass