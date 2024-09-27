from ..adapters import Adapter, IP, Timeout, Termination, StopCondition
from .protocol import Protocol
from ..tools.types import is_byte_instance
from ..tools.others import DEFAULT

DEFAULT_TIMEOUT = Timeout(response=10, continuation=0.5, total=None, on_response='error', on_continuation='error')

class SCPI(Protocol):
    DEFAULT_PORT = 5025
    def __init__(self, adapter: Adapter, send_termination = '\n', receive_termination = None, timeout : Timeout = DEFAULT, encoding : str = 'utf-8') -> None:
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
        self._encoding = encoding
        # Set the default timeout
        if timeout == DEFAULT:
            timeout = DEFAULT_TIMEOUT
        
        if receive_termination is None:
            self._receive_termination = send_termination
        else:
            self._receive_termination = receive_termination
        self._send_termination = send_termination
        # Configure the adapter for stop-condition mode (timeouts will raise errors)
        if not adapter._default_stop_condition:
            raise ValueError('No stop-conditions can be set for an adapter used by SCPI protocol')
        adapter.set_stop_condition(Termination(self._receive_termination.encode(self._encoding)))
        adapter.set_timeout(timeout)
        if isinstance(adapter, IP):
            adapter.set_default_port(self.DEFAULT_PORT)
        # Give the adapter to the Protocol base class
        super().__init__(adapter=adapter, timeout=timeout)

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

    def query(self, command : str, timeout : Timeout = DEFAULT, stop_condition : StopCondition = DEFAULT, return_metrics : bool = False) -> str:
        self._adapter.flushRead()
        self.write(command)
        return self.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)

    def read(self, timeout : Timeout = DEFAULT, stop_condition : StopCondition = None, return_metrics : bool = False) -> str:
        output = self._from_bytes(self._adapter.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics))
        return self._unformatCommand(output)

    def read_raw(self, timeout=None, stop_condition=None, return_metrics : bool = False) -> str:
        """
        Return the raw bytes instead of str

        TODO : Include custom termination option (if necessary), and specify if it should be included in the output
        """
        return self._adapter.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)