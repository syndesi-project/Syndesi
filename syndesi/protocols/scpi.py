# File : scpi.py
# Author : Sébastien Deriaz
# License : GPL


from types import EllipsisType

from syndesi.adapters.backend.adapter_backend import AdapterReadPayload

from ..adapters.adapter import Adapter
from ..adapters.ip import IP
from ..adapters.stop_condition import StopCondition, Termination
from ..adapters.timeout import Timeout, TimeoutAction
from .protocol import Protocol


class SCPI(Protocol):
    DEFAULT_PORT = 5025

    def __init__(
        self,
        adapter: Adapter,
        send_termination: str = "\n",
        receive_termination: str | None = None,
        timeout: Timeout | None | EllipsisType = ...,
        encoding: str = "utf-8",
    ) -> None:
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

        if receive_termination is None:
            self._receive_termination = send_termination
        else:
            self._receive_termination = receive_termination
        self._send_termination = send_termination
        # Configure the adapter for stop-condition mode (timeouts will raise errors)
        if not adapter._default_stop_condition:
            raise ValueError(
                "No stop-conditions can be set for an adapter used by SCPI protocol"
            )
        adapter.set_stop_conditions(
            Termination(self._receive_termination.encode(self._encoding))
        )

        # adapter.set_timeout(self.timeout)
        if isinstance(adapter, IP):
            adapter.set_default_port(self.DEFAULT_PORT)
        # Give the adapter to the Protocol base class
        super().__init__(adapter=adapter, timeout=timeout)

        # Connect the adapter if it wasn't done already
        self._adapter.connect()

    def _default_timeout(self) -> Timeout | None:
        return Timeout(response=5, action=TimeoutAction.ERROR.value)

    def _to_bytes(self, command: str) -> bytes:
        if isinstance(command, str):
            return command.encode("ASCII")
        else:
            raise ValueError(f"Invalid command type : {type(command)}")

    def _from_bytes(self, payload: bytes) -> str:
        if isinstance(payload, bytes):
            return payload.decode("ASCII")
        else:
            raise ValueError(f"Invalid payload type : {type(payload)}")

    def _formatCommand(self, command: str) -> str:
        return command + self._send_termination

    def _unformatCommand(self, payload: str) -> str:
        return payload.replace(self._receive_termination, "")

    def _checkCommand(self, command: str) -> None:
        for c in ["\n", "\r"]:
            if c in command:
                raise ValueError(f"Invalid char {repr(c)} in command")

    def write(self, command: str) -> None:
        self._checkCommand(command)
        payload = self._to_bytes(self._formatCommand(command))
        self._adapter.write(payload)

    def write_raw(self, data: bytes, termination: bool = False) -> None:
        self._adapter.write(
            data
            + (self._send_termination.encode(self._encoding) if termination else b"")
        )

    def query(
        self,
        command: str,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> str:
        self._adapter.flushRead()
        self.write(command)

        return self.read(timeout=timeout, stop_conditions=stop_conditions)

    def read_raw(
        self,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> bytes:
        signal = self.read_detailed(
            timeout=timeout,
            stop_conditions=stop_conditions,
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
        raw_data = signal.data()
        return self._unformatCommand(self._from_bytes(raw_data))
