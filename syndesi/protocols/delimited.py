# File : delimited.py
# Author : Sébastien Deriaz
# License : GPL
"""
Delimited protocol, formats data when communicating with devices expecting
command-like formats with specified delimiters (like \\n, \\r, \\r\\n, etc...)
"""
from types import EllipsisType

from syndesi.adapters.bytesadapter import BytesAdapter

from ..adapters.stop_conditions import StopCondition, Termination
from ..adapters.timeout import Timeout
from ..component import Frame, ReadScope
from .protocol import Protocol, ProtocolEvent, ProtocolFrame

# class DelimitedFrame(ProtocolFrame[str]):
#     """Delimited frame"""

#     payload: str

#     def __str__(self) -> str:
#         return f"DelimitedFrame({self.payload})"


class Delimited(Protocol[str, bytes]):
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

    def __init__(
        self,
        adapter: BytesAdapter,
        termination: str = "\n",
        *,
        format_response: bool = True,
        encoding: str = "utf-8",
        timeout: Timeout | None | EllipsisType = ...,
        receive_termination: str | None = None,
    ) -> None:
        self._encoding = encoding
        if isinstance(termination, bytes):
            termination = termination.decode(self._encoding)
        elif not isinstance(termination, str):
            raise ValueError(
                f"end argument must be of type str or bytes, not {type(termination)}"
            )
        if receive_termination is None:
            self._receive_termination = termination
        else:
            self._receive_termination = receive_termination
        self._termination = termination
        self._response_formatting = format_response

        adapter.set_stop_conditions(
            stop_conditions=Termination(sequence=self._receive_termination)
        )
        super().__init__(adapter, timeout=timeout)

    def __str__(self) -> str:
        if self._receive_termination == self._termination:
            return f"Delimited({self._adapter},{repr(self._termination)})"
        return (
            f"Delimited({self._adapter},{repr(self._termination)}"
            "/{repr(self._receive_termination)})"
        )

    def __repr__(self) -> str:
        return self.__str__()

    def _default_timeout(self) -> Timeout | None:
        return Timeout(response=2)

    # ┌────────────┐
    # │ Public API │
    # └────────────┘

    # ==== read_detailed ====

    def _adapter_to_protocol(self, adapter_frame: Frame[bytes]) -> ProtocolFrame[str]:
        data = adapter_frame.data.decode(self._encoding)
        if data.endswith(self._receive_termination):
            data = data[: -len(self._receive_termination)]

        return ProtocolFrame(
            data=data,
            stop_timestamp=adapter_frame.stop_timestamp,
            stop_condition_type=adapter_frame.stop_condition_type,
            previous_read_buffer_used=adapter_frame.previous_read_buffer_used,
            response_delay=adapter_frame.response_delay,
        )

    def _protocol_to_adapter(self, protocol_payload: str) -> bytes:
        terminated_payload = protocol_payload + self._termination
        return terminated_payload.encode(self._encoding)

    def read_raw(
        self,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        scope: str = ReadScope.BUFFERED.value,
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
        frame = self._adapter.read_detailed(
            timeout=timeout, stop_conditions=stop_conditions, scope=scope
        )
        return frame.data
