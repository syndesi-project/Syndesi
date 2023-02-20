# Sébastien Deriaz
# 20.02.2023
#
# Communication wrapper abstract class


from abc import abstractmethod, ABCMeta

class Wrapper(ABCMeta):
    @abstractmethod
    def __init__(self, descriptor, *args):
        pass

    @abstractmethod
    def open():
        pass

    @abstractmethod
    def close():
        pass
            
    @abstractmethod
    def write():
        pass
    
    @abstractmethod
    def read():
        pass