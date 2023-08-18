from ..adapters import IAdapter, IP
from .iprotocol import IProtocol


class SCPI(IProtocol):
    DEFAULT_PORT = 5025
    def __init__(self, adapter: IAdapter, end = '\n') -> None:
        """
        SDP (Syndesi Device Protocol) compatible device

        Parameters
        ----------
        wrapper : Wrapper
        """
        super().__init__(adapter)
        self._end = end

        if isinstance(self._adapter, IP):
            self._adapter.set_default_port(self.DEFAULT_PORT)

    def _to_bytearray(self, command):
        if isinstance(command, str):
            return command.encode('ASCII')
        else:
            raise ValueError(f'Invalid command type : {type(command)}')
    
    def _from_bytearray(self, payload):
        if isinstance(payload, bytearray):
            return payload.decode('ASCII')
        else:
            raise ValueError(f"Invalid payload type : {type(payload)}")

    def _formatCommand(self, command):
        return command + self._end

    def _unformatCommand(self, payload):
        return payload.replace(self._end, '')
    
    def _checkCommand(self, command : str):
        for c in ['\n', '\r']:
            if c in command:
                raise ValueError(f"Invalid char '{c}' in command")

    def write(self, command : str) -> None:
        self._checkCommand(command)
        payload = self._to_bytearray(self._formatCommand(command))
        self._adapter.write(payload)

    def query(self, command : str) -> str:
        self._adapter.flushRead()
        self.write(command)
        return self.read()

    def read(self) -> str:
        output = self._from_bytearray(self._adapter.read())
        return self._unformatCommand(output)

    def read_raw(self) -> str:
        """
        Return the raw bytes instead of str
        """
        return self._adapter.read()