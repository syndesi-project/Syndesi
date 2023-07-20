from ..adapters import IAdapter, IP
from .iprotocol import IProtocol


class SCPI(IProtocol):
    DEFAULT_PORT = 5025
    def __init__(self, adapter: IAdapter) -> None:
        """
        SDP (Syndesi Device Protocol) compatible device

        Parameters
        ----------
        wrapper : Wrapper
        """
        super().__init__(adapter)
        self._end = b'\n'

        if isinstance(self._adapter, IP):
            self._adapter.set_default_port(self.DEFAULT_PORT)

    def _to_bytearray(self, command):
        if isinstance(command, str):
            return command.encode('ASCII')
        elif isinstance(command, bytes) or isinstance(command, bytearray):
            return command
        else:
            raise ValueError(f'Invalid command type : {type(command)}')

    def _formatCommand(self, command):
        return command + self._end
    
    def _checkCommand(self, command : bytearray):
        for c in [b'\n', b'\r']:
            if c in command:
                raise ValueError(f"Invalid char '{c}' in command")

    def write(self, command : bytearray) -> None:
        command = self._to_bytearray(command)
        self._checkCommand(command)
        self._adapter.write(self._formatCommand(command))

    def query(self, data : bytearray) -> bytearray:
        command = self._to_bytearray(data)
        self._adapter.flushRead()
        self.write(data)
        return self.read()

    def read(self) -> bytearray:
        return self._adapter.read()