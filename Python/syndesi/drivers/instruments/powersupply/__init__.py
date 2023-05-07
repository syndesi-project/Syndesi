from abc import ABC, abstractmethod

class IPowersupplyDC():
    # Provides power supply functions (one channel only)
    @abstractmethod
    def set_voltage(self, volts : float):
        pass
    
    @abstractmethod
    def get_voltage(self) -> float:
        pass
    
    @abstractmethod
    def set_current(self, amps : float):
        pass
    
    @abstractmethod
    def get_current(self) -> float:
        pass
    
    @abstractmethod
    def set_output_state(self, state : bool):
        pass
    
    @abstractmethod
    def measure_dc_voltage(self) -> float:
        pass
    
    @abstractmethod
    def measure_dc_current(self) -> float:
        pass

class IMultiChannelPowersupplyDC():
    # Provides power supply functions (multi channel)
    @abstractmethod
    def set_voltage(self, Channel : int, volts : float):
        pass
    
    @abstractmethod
    def set_voltage(self, channel : int) -> float:
        pass
    
    @abstractmethod
    def set_current(self, channel : int, amps : float):
        pass
    
    @abstractmethod
    def get_current(self, channel : int) -> float:
        pass
    
    @abstractmethod
    def set_output_state(self, channel : int, state : bool):
        pass

    @abstractmethod
    def measure_dc_current(self, channel) -> float:
        pass
    
    @abstractmethod
    def measure_dc_voltage(self, channel) -> float:
        pass