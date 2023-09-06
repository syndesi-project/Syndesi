
from pyvisa import ResourceManager

from .iadapter import IAdapter
from ..tools.types import assert_byte_instance

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
        self._inst.write_termination = ''
        self._inst.read_termination = ''

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
            
    def write(self, data : bytes):
        assert_byte_instance(data)
        self._inst.write_raw(data)
    
    def read(self) -> bytes:
        return self._inst.read_raw()

    def query(self, data : bytes, timeout=None, continuation_timeout=None) -> bytes:
        """
        Shortcut function that combines
        - flush_read
        - write
        - read
        """
        # TODO : implement timeouts
        return self._inst.query(data.encode('ASCII'))