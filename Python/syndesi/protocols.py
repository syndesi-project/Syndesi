from .adapters import IAdapter, IP


class Protocol:
    def __init__(self, adapter : IAdapter) -> None:
        self._adapter = adapter

class Raw(Protocol):
    def __init__(self, adapter: IAdapter) -> None:
        """
        Raw device, no presentation and application protocol

        Parameters
        ----------
        adapter : IAdapter
        """
        super().__init__(adapter)

class SCPI():
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
            if self._adapter._port is None:
                self._adapter._port = self.DEFAULT_PORT

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


class SDP(Protocol):
    def __init__(self, adapter: IAdapter) -> None:
        """
        SDP (Syndesi Device Protocol) compatible device

        Parameters
        ----------
        wrapper : Wrapper
        """
        super().__init__(adapter)
        