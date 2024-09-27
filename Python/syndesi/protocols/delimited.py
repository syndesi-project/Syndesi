from .protocol import Protocol
from ..adapters import Adapter, Timeout, Termination
from ..tools.types import assert_byte_instance, assert_byte_instance
from ..tools.others import DEFAULT
from time import time
import warnings


class Delimited(Protocol):
    def __init__(self, adapter : Adapter, termination='\n', format_response=True, encoding : str = 'utf-8', timeout : Timeout = DEFAULT) -> None:
        """
        Protocol with delimiter, like LF, CR, etc... '\\n' is used by default

        No presentation or application layers

        Parameters
        ----------
        adapter : IAdapter
        termination : bytes
            Command termination, '\\n' by default
        format_response : bool
            Apply formatting to the response (i.e removing the termination), True by default
        encoding : str
        timeout : Timeout
            None by default (default timeout)
        """
        adapter.set_default_stop_condition(stop_condition=Termination(sequence=termination))
        super().__init__(adapter, timeout=timeout)

        if not isinstance(termination, str):
            raise ValueError(f"end argument must be of type str, not {type(termination)}")

        self._encoding = encoding
        self._termination = termination
        self._response_formatting = format_response

    def _to_bytes(self, command) -> bytes:
        if isinstance(command, str):
            return command.encode('ASCII')
        elif assert_byte_instance(command):
            return command
        else:
            raise ValueError(f'Invalid command type : {type(command)}')
    
    def _from_bytes(self, payload) -> str:
        assert_byte_instance(payload)
        return payload.decode('ASCII')        

    def _format_command(self, command : str) -> str:
        return command + self._termination
    
    def _format_response(self, response : str) -> str:
        if response.endswith(self._termination):
            response = response[:-len(self._termination)]
        return response

    def write(self, command : str):
        command = self._format_command(command)
        self._adapter.write(self._to_bytes(command))

    def query(self, command : str) -> str:
        """
        Writes then reads from the device and return the result
        """
        self._adapter.flushRead()
        self.write(command)
        return self.read()

    def read(self, timeout : Timeout = DEFAULT, decode : str = True) -> str:
        """
        Reads command and formats it as a str

        Parameters
        ----------
        timeout : Timeout
        decode : bool
            Decode incoming data, True by default
        """

        # Send up to the termination
        data = self._adapter.read(timeout=timeout)
        if decode:
            try:
                data = data.decode(self._encoding)
            except UnicodeDecodeError as e:
                raise ValueError(f'Failed to decode {data} to {self._encoding} ({e})')
        if self._response_formatting:
            # Only send the fragment (no termination)
            return data
        else:
            # Add the termination back in
            return data + self._termination 