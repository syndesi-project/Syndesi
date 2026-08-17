# File : delimited.py
# Author : Sébastien Deriaz
# License : GPL
"""
Delimited protocol, formats data when communicating with devices expecting
command-like formats with specified delimiters (like \\n, \\r, \\r\\n, etc...)
"""
from types import EllipsisType

from syndesi.adapters.bytesadapter import BytesAdapter
from syndesi.adapters.utils import TimeoutParameterType

from ..adapters.stop_conditions import StopCondition, Termination
from ..component import ReadFrame, ReadScope
from .protocol import BytesProtocol, ProtocolReadFrame


class Delimited(BytesProtocol[str]):
    """
    Protocol with string decoding and delimiter, like LF, CR, etc... LF is used by default

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
    timeout : float | int | None | ...
        None by default (default timeout)
    receive_termination : bytes
        Termination when receiving only, optional
        if not set, the value of termination is used
    """

    def __init__(
        self,
        adapter: BytesAdapter,
        termination: str | bytes = "\n",
        *,
        format_response: bool = True,
        encoding: str = "utf-8",
        timeout: TimeoutParameterType = ...,
        receive_termination: str | None = None,
    ) -> None:
        self._encoding = encoding
        if isinstance(termination, bytes):
            termination = termination.decode(self._encoding)
        elif not isinstance(termination, str):
            raise ValueError(
                f"termination argument must be of type str or bytes, not {type(termination)}"
            )
        self._termination = termination

        if receive_termination is None:
            self._receive_termination = termination
        else:
            self._receive_termination = receive_termination

            if isinstance(receive_termination, bytes):
                receive_termination = receive_termination.decode(self._encoding)
            elif not isinstance(receive_termination, str):
                raise ValueError(
                    f"termination argument must be of type str or bytes, not {type(termination)}"
                )
        
        adapter.set_stop_conditions(
            stop_conditions=Termination(sequence=self._receive_termination)
        )

        super().__init__(adapter, timeout=timeout)

    def __str__(self) -> str:
        if self._receive_termination == self._termination:
            return f"Delimited({self.adapter},{repr(self._termination)})"
        return (
            f"Delimited({self.adapter},{repr(self._termination)}"
            f"/{repr(self._receive_termination)})"
        )

    def __repr__(self) -> str:
        return self.__str__()

    @staticmethod
    def default_timeout() -> float | None:
        """Default timeout"""
        return 2.0

    def _adapter_to_protocol(self, adapter_frame: ReadFrame[bytes]) -> ProtocolReadFrame[str]:
        data = adapter_frame.data.decode(self._encoding)
        if data.endswith(self._receive_termination):
            data = data[: -len(self._receive_termination)]

        return ProtocolReadFrame(
            data=data,
            id=adapter_frame.id,
            stop_timestamp=adapter_frame.stop_timestamp,
            stop_condition=adapter_frame.stop_condition,
            previous_read_buffer_used=adapter_frame.previous_read_buffer_used,
            response_delay=adapter_frame.response_delay,
        )

    def _protocol_to_adapter(self, protocol_payload: str) -> bytes:
        terminated_payload = protocol_payload + self._termination
        return terminated_payload.encode(self._encoding)
    
    def set_termination(self, termination : str | bytes, receive_termination : str | bytes | None = None) -> None:
        """Set Delimited termination.
        If receive_termination is not specified, termination parameter is used both
        for send and receive

        Parameters
        ----------
        termination : str | bytes
        receive_termination : str | bytes
            Optional, specific termination for receive only
        """
        if isinstance(termination, bytes):
            termination = termination.decode(self._encoding)
        elif not isinstance(termination, str):
            raise ValueError(
                f"termination argument must be of type str or bytes, not {type(termination)}"
            )
        self._termination = termination
        
        if receive_termination is None:
            self._receive_termination = self._termination
        else:
            if isinstance(receive_termination, bytes):
                receive_termination = receive_termination.decode(self._encoding)
            elif not isinstance(receive_termination, str):
                raise ValueError(
                    f"receive_termination argument must be of type str or bytes, not {type(termination)}"
                )
            self._receive_termination = receive_termination
        
        self.adapter.set_stop_conditions(
            stop_conditions=Termination(sequence=self._receive_termination)
        )

    @property
    def termination(self) -> str: 
        return self._termination

    @property
    def receive_termination(self) -> str:
        return self._receive_termination       
    
    # ┌────────────┐
    # │ Public API │
    # └────────────┘

    def read_raw(
        self,
        timeout: TimeoutParameterType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
    ) -> bytes:
        """
        Reads command and formats it as a str

        Parameters
        ----------
        timeout : float | int | None | ...
        decode : bool
            Decode incoming data, True by default
        full_output : bool
            If True, Return data and read information in a additionnal BackendReadOutput class
            If False, Return data only
        """
        # Send up to the termination
        frame = self.adapter.read_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )
        return frame.data
