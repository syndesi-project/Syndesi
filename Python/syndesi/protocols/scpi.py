from ..adapters import Adapter, IP, Timeout, Termination, StopCondition
from .protocol import Protocol
from ..tools.types import is_byte_instance
#from ..tools.others import is_default_argument
from ..tools.others import DEFAULT

class SCPI(Protocol):
    DEFAULT_PORT = 5025
    def __init__(self, adapter: Adapter, send_termination = '\n', receive_termination = None, timeout : Timeout = None, encoding : str = 'utf-8') -> None:
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
        super().__init__(adapter=adapter, timeout=timeout)

        if receive_termination is None:
            self._receive_termination = send_termination
        else:
            self._receive_termination = receive_termination

        self._send_termination = send_termination

        if isinstance(self._adapter, IP):
            self._adapter.set_default_port(self.DEFAULT_PORT)

        self._adapter.set_default_timeout(timeout)
        if self._adapter._stop_condition != DEFAULT:
            raise ValueError('A conflicting stop-condition has been set for this adapter')
        self._adapter._stop_condition = Termination(self._receive_termination.encode(encoding=encoding))

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
                raise ValueError(f"Invalid char {repr(c)} in command")

    def write(self, command : str) -> None:
        self._checkCommand(command)
        payload = self._to_bytes(self._formatCommand(command))
        self._adapter.write(payload)

    def query(self, command : str, timeout : Timeout = None, stop_condition : StopCondition = None, return_metrics : bool = False) -> str:
        self._adapter.flushRead()
        self.write(command)
        return self.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)

    def read(self, timeout : Timeout = None, stop_condition : StopCondition = None, return_metrics : bool = False) -> str:
        output = self._from_bytes(self._adapter.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics))
        return self._unformatCommand(output)

    def read_raw(self, timeout=None, stop_condition=None, return_metrics : bool = False) -> str:
        """
        Return the raw bytes instead of str

        TODO : Include custom termination option (if necessary), and specify if it should be included in the output
        """
        return self._adapter.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)