
from pyvisa import ResourceManager

from .iadapter import IAdapter

class VISA(IAdapter):
    def __init__(self, descriptor : str):
        """
        USB VISA stack adapter

        Parameters
        ----------
        descriptor : str
            IP description
        """
        self._rm = ResourceManager()
        self._inst = self._rm.open_resource(descriptor)

    def list_devices(self=None):
        """
        Returns a list of VISA devices
        """
        rm = ResourceManager()

        return rm.list_resources()

    def flushRead(self):
        pass

    def open(self):
        self._inst.open()

    def close(self):
        self._inst.close()
            
    def write(self, data : bytearray):
        self._inst.write(data.decode('ASCII'))
    
    def read(self):
        return self._inst.read()

    def write_read(self, data : bytearray, timeout=None, continuation_timeout=None):
        """
        Shortcut function that combines
        - flush_read
        - write
        - read
        """
        # TODO : implement timeouts
        return self._inst.query(data.encode('ASCII'))