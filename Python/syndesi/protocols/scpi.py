from ..adapters import Adapter, IP, Timeout
from .protocol import Protocol
from ..tools.types import is_byte_instance

class SCPI(Protocol):
    DEFAULT_PORT = 5025
    def __init__(self, adapter: Adapter, send_termination = '\n', receive_termination = None, timeout : Timeout = None) -> None:
        """
        SDP (Syndesi Device Protocol) compatible device

        Parameters
        ----------
        adapter : Adapter
        send_termination : str
            '\n' by default
        receive_termination : str
            None by default (copy value from send_termination)
        timeout : Timeout/float/tuple
            Set device timeout
        """
        super().__init__(adapter)

        if receive_termination is None:
            self._receive_termination = send_termination
        else:
            self._receive_termination = receive_termination

        self._send_termination = send_termination

        if isinstance(self._adapter, IP):
            self._adapter.set_default_port(self.DEFAULT_PORT)

        self._adapter.set_default_timeout(timeout)
        

    def _to_bytes(self, command):
        if isinstance(command, str):
            return command.encode('ASCII')
        else:
            raise ValueError(f'Invalid command type : {type(command)}')
    
    def _from_bytes(self, payload : bytes):
        if is_byte_instance(payload):
            return payload.decode('ASCII')
        else:
            raise ValueError(f"Invalid payload type : {type(payload)}")

    def _formatCommand(self, command):
        return command + self._send_termination

    def _unformatCommand(self, payload):
        return payload.replace(self._receive_termination, '')
    
    def _checkCommand(self, command : str):
        for c in ['\n', '\r']:
            if c in command:
                raise ValueError(f"Invalid char '{c}' in command")

    def get_identification(self):
        """
        Return identification returned by '*IDN?\n'

        Returns
        -------
        identification : str
        """
        identification = self.query('*IDN?\n')
        return identification

    def write(self, command : str) -> None:
        self._checkCommand(command)
        payload = self._to_bytes(self._formatCommand(command))
        self._adapter.write(payload)

    def query(self, command : str) -> str:
        self._adapter.flushRead()
        self.write(command)
        return self.read()

    def read(self) -> str:
        output = self._from_bytes(self._adapter.read())
        return self._unformatCommand(output)

    def read_raw(self) -> str:
        """
        Return the raw bytes instead of str
        """
        return self._adapter.read()