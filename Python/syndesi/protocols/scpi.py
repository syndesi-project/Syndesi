#from .protocol import Primary
from ..adapters import IAdapter, IP
#from .  ..wrappers.wrapper import Wrapper
#from ..wrappers.ip import IP

SCPI_PORT = 5025

class SCPI():
    def __init__(self, adapter : IAdapter):
        """
        SDP (Syndesi Device Protocol) compatible device

        Parameters
        ----------
        wrapper : Wrapper
        """
        self._adapter = adapter
        self._end = b'\n'

        if isinstance(self._adapter, IP):
            if self._adapter._port is None:
                self._adapter._port = SCPI_PORT

    def _formatCommand(self, command):
        return command + self._end
    
    def _checkCommand(self, command : bytearray):
        for c in [b'\n', b'\r']:
            if c in command:
                raise ValueError(f"Invalid char '{c}' in command")

    def write(self, command : bytearray):
        self._checkCommand(command)
        self._adapter.write(self._formatCommand(command))


    def query(self, data : bytearray):
        self._adapter.flushRead()
        self.write(data)
        return self.read()

    def read(self):
        return self._adapter.read()