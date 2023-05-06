from abc import ABC, abstractmethod

class Voltmeter(ABC):
    # Provides a voltage measurement
    @abstractmethod
    def measureDC(self) -> float:
        pass
    
    @abstractmethod
    def measureAC(self) -> float:
        pass


class Ammeter(ABC):
    # Provides a current measurement
    @abstractmethod
    def measureDC(self) -> float:
        pass
    
    @abstractmethod
    def measureAC(self) -> float:
        pass