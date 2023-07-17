from .iadapter import IAdapter

class Serial(IAdapter):
    def __init__(self, descriptor : str):
        """
        Serial communication adapter

        Parameters
        ----------
        descriptor : str
            Serial port (COMx or ttyACMx)
        """
        pass

    def flushRead(self):
        pass

    def open(self):
        pass

    def close(self):
        pass
            
    def write(self, data : bytearray):
        pass
    
    def read(self):
        pass