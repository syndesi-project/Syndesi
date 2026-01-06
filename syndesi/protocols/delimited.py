# File : delimited.py
# Author : Sébastien Deriaz
# License : GPL
"""
Delimited protocol, formats data when communicating with devices expecting
command-like formats with specified delimiters (like \\n, \\r, \\r\\n, etc...)
"""

from collections.abc import Callable
from types import EllipsisType

from syndesi.adapters.adapter_worker import (
    AdapterDisconnectedEvent,
    AdapterEvent,
    AdapterFrameEvent,
)

from ..adapters.adapter import Adapter
from ..adapters.stop_conditions import StopCondition, Termination
from ..adapters.timeout import Timeout
from ..component import AdapterFrame, ReadScope
from .protocol import (
    Protocol,
    ProtocolDisconnectedEvent,
    ProtocolEvent,
    ProtocolFrame,
    ProtocolFrameEvent,
)


class DelimitedFrame(ProtocolFrame[str]):
    """Delimited frame"""

    payload: str

    def __str__(self) -> str:
        return f"DelimitedFrame({self.payload})"


class Delimited(Protocol[str]):
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
        adapter: Adapter,
        termination: str = "\n",
        *,
        format_response: bool = True,
        encoding: str = "utf-8",
        timeout: Timeout | None | EllipsisType = ...,
        event_callback: Callable[[ProtocolEvent], None] | None = None,
        receive_termination: str | None = None,
    ) -> None:
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

        self._adapter.set_event_callback(self._on_event)

        # TODO : Disable encoding/decoding when encoding==None

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
        return Timeout(response=2, action="error")

    # ┌────────────┐
    # │ Public API │
    # └────────────┘

    # ==== read_detailed ====

    def _adapter_to_protocol(self, adapter_frame: AdapterFrame) -> DelimitedFrame:
        data = adapter_frame.get_payload().decode(self._encoding)
        if data.endswith(self._receive_termination):
            data = data[: -len(self._receive_termination)]

        return DelimitedFrame(
            payload=data,
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
        return frame.get_payload()

    def _on_event(self, event: AdapterEvent) -> None:

        if self._event_callback is not None:
            output_event: ProtocolEvent | None = None
            if isinstance(event, AdapterDisconnectedEvent):
                output_event = ProtocolDisconnectedEvent()
            if isinstance(event, AdapterFrameEvent):
                output_event = ProtocolFrameEvent(
                    frame=self._adapter_to_protocol(event.frame)
                )

            if output_event is not None:
                self._event_callback(output_event)
