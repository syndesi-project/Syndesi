# File : delimited.py
# Author : Sébastien Deriaz
# License : GPL

from collections.abc import Callable
from types import EllipsisType

from ..adapters.adapter import Adapter
from ..adapters.backend.adapter_backend import AdapterReadPayload, AdapterSignal
from ..adapters.stop_condition import StopCondition, Termination
from ..adapters.timeout import Timeout
from .protocol import Protocol


class Delimited(Protocol):
    def __init__(
        self,
        adapter: Adapter,
        termination: str = "\n",
        format_response: bool = True,
        encoding: str = "utf-8",
        timeout: Timeout | None | EllipsisType = ...,
        event_callback: Callable[[AdapterSignal], None] | None = None,
        receive_termination: str | None = None,
    ) -> None:
        """
        Protocol with delimiter, like LF, CR, etc... LF is used by default

        No presentation or application layers

        Parameters
        ----------
        adapter : Adapter
        termination : bytes
            Command termination, '\\n' by default
        format_response : bool
            Apply formatting to the response (i.e removing the termination), True by default
        encoding : str or None
            If None, delimited will not encode/decode
        timeout : Timeout
            None by default (default timeout)
        receive_termination : bytes
            Termination when receiving only, optional
            if not set, the value of termination is used
        """
        if not isinstance(termination, str) or isinstance(termination, bytes):
            raise ValueError(
                f"end argument must be of type str or bytes, not {type(termination)}"
            )
        if receive_termination is None:
            self._receive_termination = termination
        else:
            self._receive_termination = receive_termination
        self._termination = termination
        self._encoding = encoding
        self._response_formatting = format_response

        adapter.set_stop_conditions(
            stop_conditions=Termination(sequence=self._receive_termination)
        )
        super().__init__(adapter, timeout=timeout, event_callback=event_callback)

        # Connect the adapter if it wasn't done already
        self._adapter.connect()

        # TODO : Disable encoding/decoding when encoding==None

    def __str__(self) -> str:
        if self._receive_termination == self._termination:
            return f"Delimited({self._adapter},{repr(self._termination)})"
        else:
            return f"Delimited({self._adapter},{repr(self._termination)}/{repr(self._receive_termination)})"

    def _default_timeout(self) -> Timeout | None:
        return Timeout(response=2, action="error")

    def __repr__(self) -> str:
        return self.__str__()

    def _to_bytes(self, command: str | bytes) -> bytes:
        if isinstance(command, str):
            return command.encode("ASCII")
        elif isinstance(command, bytes):
            return command
        else:
            raise ValueError(f"Invalid command type : {type(command)}")

    def _from_bytes(self, payload: bytes) -> str:
        assert isinstance(payload, bytes)
        return payload.decode("ASCII")  # TODO : encoding ?

    def _format_command(self, command: str) -> str:
        return command + self._termination

    def _format_response(self, response: str) -> str:
        if response.endswith(self._receive_termination):
            response = response[: -len(self._receive_termination)]
        return response

    def _on_data_ready_event(self, data: AdapterReadPayload) -> None:
        # TODO : Call the callback here ?
        # output = self._format_read(data.data(), decode=True)
        # return output
        pass

    def write(self, command: str) -> None:
        command = self._format_command(command)
        self._adapter.write(self._to_bytes(command))

    def query(self, data: str, timeout: Timeout | None | EllipsisType = ...) -> str:
        """
        Writes then reads from the device and return the result

        Parameters
        ----------
        data : str
            Data to send to the device
        timeout : Timeout
            Custom timeout for this query (optional)
        decode : bool
            Decode incoming data, True by default
        full_output : bool
            return metrics on read operation (False by default)
        """
        self._adapter.flushRead()
        self.write(data)
        return self.read(timeout=timeout)

    def read_raw(
        self,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> bytes:
        """
        Reads command and formats it as a str

        Parameters
        ----------
        timeout : Timeout
        decode : bool
            Decode incoming data, True by default
        full_output : bool
            If True, Return data and read information in a additionnal BackendReadOutput class
            If False, Return data only
        """

        # Send up to the termination
        signal = self._adapter.read_detailed(
            timeout=timeout, stop_conditions=stop_conditions
        )
        return signal.data()

    def read_detailed(
        self,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> AdapterReadPayload:
        signal = self._adapter.read_detailed(
            timeout=timeout, stop_conditions=stop_conditions
        )
        return signal

    def read(
        self,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> str:
        signal = self.read_detailed(timeout=timeout, stop_conditions=stop_conditions)
        return self._decode(signal.data())

    def _decode(self, data: bytes) -> str:
        try:
            data_string = data.decode(self._encoding)
        except UnicodeDecodeError as err:
            raise ValueError(
                f"Failed to decode {data!r} to {self._encoding} ({err})"
            ) from err
        else:
            if not self._response_formatting:
                # Add the termination back in since it was removed by the adapter
                data_string += self._receive_termination

        return data_string