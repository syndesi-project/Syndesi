from .protocol import Protocol
from ..adapters import Adapter
from ..tools.types import assert_byte_instance, assert_byte_instance
from time import time
import warnings


class Delimited(Protocol):
    def __init__(self, adapter : Adapter, termination='\n', format_response=True) -> None:
        """
        Protocol with delimiter, like LF, CR, etc... '\\n' is used by default

        No presentation or application layers

        Parameters
        ----------
        adapter : IAdapter
        end : bytes
            Command termination, '\\n' by default
        format_response : bool
            Apply formatting to the response (i.e removing the termination)
        """
        super().__init__(adapter)

        # Temporary solution before implementing stop conditions
        self._buffer = ''

        if not isinstance(termination, str):
            raise ValueError(f"end argument must be of type str, not {type(termination)}")
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

    # Note : for later revisions of the delimited module, the buffer should be removed as the
    # adapter will take care of that using the stop conditions
    #
    # For now the delimited module will take care of it
    #
    # Stop conditions should also be added inside the delimited module (unclear yet how)

    def read(self, timeout=2) -> str:
        """
        Reads command and formats it as a str
        """
        if self._termination not in self._buffer:
            # Read the adapter only if there isn't a fragment already in the buffer
            start = time()
            while True:
                # Continuously read the adapter as long as no termination is caught
                data = self._from_bytes(self._adapter.read())
                self._buffer += data
                if self._termination in data or time() > start + timeout:
                    break

        # Send up to the termination
        fragment, self._buffer = self._buffer.split(self._termination, maxsplit=1)
        if self._response_formatting:
            # Only send the fragment (no termination)
            return fragment
        else:
            # Add the termination back in
            return fragment + self._termination

    def read_raw(self) -> bytes:
        """
        Returns the raw bytes instead of str
        """
        if len(self._buffer) > 0:
            warnings.warn("Warning : The buffer wasn't empty, standard (non raw) data is still in it")
        return self._adapter.read()