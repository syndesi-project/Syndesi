# Sébastien Deriaz
# 20.02.2023
#
# Communication wrapper abstract class

from abc import abstractmethod, ABCMeta, ABC

class Wrapper(ABC):
    @abstractmethod
    def __init__(self, descriptor, *args):
        pass

    @abstractmethod
    def open(self):
        pass

    @abstractmethod
    def close(self):
        pass
            
    @abstractmethod
    def write(self, data : bytearray):
        pass
    
    @abstractmethod
    def read(self):
        pass