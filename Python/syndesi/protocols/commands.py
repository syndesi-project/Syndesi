from .iprotocol import IProtocol
from ..adapters import IAdapter


class Commands(IProtocol):
    def __init__(self, adapter : IAdapter, termination='\n', format_response=True) -> None:
        """
        Command-based protocol, with LF, CR or CRLF termination

        No presentation or application layers

        Parameters
        ----------
        adapter : IAdapter
        end : bytearray
            Command termination, '\n' by default
        format_response : bool
            Apply formatting to the response (i.e removing the termination)
        """
        super().__init__(adapter)

        if not isinstance(termination, str):
            raise ValueError(f"end argument must be of type str, not {type(termination)}")
        self._termination = termination
        self._response_formatting = format_response

    def _to_bytearray(self, command) -> bytearray:
        if isinstance(command, str):
            return command.encode('ASCII')
        elif isinstance(command, bytes) or isinstance(command, bytearray):
            return command
        else:
            raise ValueError(f'Invalid command type : {type(command)}')
    
    def _from_bytearray(self, payload) -> str:
        if isinstance(payload, bytearray):
            return payload.decode('ASCII')
        else:
            raise ValueError(f"Invalid payload type : {type(payload)}")
        

    def _format_command(self, command : str) -> str:
        return command + self._termination
    
    def _format_response(self, response : str) -> str:
        if response.endswith(self._termination):
            response = response[:-len(self._termination)]
        return response

    def write(self, command : str):
        command = self._format_command(command)
        self._adapter.write(self._to_bytearray(command))

    def query(self, command : str) -> str:
        """
        Writes then reads from the device then return the result
        
        """
        self._adapter.flushRead()
        self.write(command)
        return self.read()


    def read(self) -> str:
        """
        Reads command and formats it as an str
        """
        output = self._from_bytearray(self._adapter.read())
        if self._response_formatting:
            return self._format_response(output)
        else:
            return output

    def read_raw(self) -> bytearray:
        """
        Returns the raw bytes instead of str
        """
        return self._adapter.read()