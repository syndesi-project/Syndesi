from .iprotocol import IProtocol
from ..adapters import IAdapter


class RawCommands(IProtocol):
    def __init__(self, adapter : IAdapter, end=b'\n', format_response=True) -> None:
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

        if not isinstance(end, bytes):
            raise ValueError(f"end argument must be of type bytes, not {type(end)}")
        self._end = end
        self._response_formatting = format_response

    def _to_bytearray(self, command) -> bytearray:
        if isinstance(command, str):
            return command.encode('ASCII')
        elif isinstance(command, bytes) or isinstance(command, bytearray):
            return command
        else:
            raise ValueError(f'Invalid command type : {type(command)}')

    def _format_command(self, command : bytearray) -> bytearray:
        return command + self._end
    
    def _format_response(self, response : bytearray) -> bytearray:
        if response.endswith(self._end):
            response = response[:-len(self._end)]
        return response

    def write(self, command : bytearray):
        command = self._to_bytearray(command)
        self._adapter.write(self._format_command(command))

    def query(self, command : bytearray) -> bytearray:
        data = self._to_bytearray(command)
        self._adapter.flushRead()
        self.write(data)
        return self.read()

    def read(self) -> bytearray:
        if self._response_formatting:
            return self._format_response(self._adapter.read())
        else:
            return self._adapter.read()