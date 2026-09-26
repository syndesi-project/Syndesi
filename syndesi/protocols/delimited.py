# File : delimited.py
# Author : Sébastien Deriaz
# License : GPL
"""
Delimited protocol, for devices exchanging text commands ended by a delimiter
(\\n, \\r, \\r\\n, ...)
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..adapters.adapter import Adapter, AsyncAdapter
from ..adapters.framer import AdapterReadFrame
from ..adapters.stop_conditions import StopCondition, Termination
from ..adapters.utils import TimeoutParameterType, TimeoutType
from .protocol import (
    AsyncProtocol,
    BackendOutput,
    Protocol,
    ProtocolBackend,
)


class DelimitedBackend(ProtocolBackend[bytes, str]):
    """
    Text commands ended by a termination

    One adapter frame is one payload : the adapter already cuts on the termination, so
    there is nothing to assemble here

    Parameters
    ----------
    termination : str or bytes
        Appended to every payload written
    receive_termination : str, bytes or None
        Ends every frame received, the value of termination if None
    encoding : str
    format_response : bool
        Remove receive_termination from the payloads read
    """

    def __init__(
        self,
        termination: str | bytes = "\n",
        receive_termination: str | bytes | None = None,
        encoding: str = "utf-8",
        format_response: bool = True,
    ) -> None:
        super().__init__()
        self.encoding = encoding
        self.termination = self._as_str(termination, "termination")
        self.receive_termination = (
            self.termination
            if receive_termination is None
            else self._as_str(receive_termination, "receive_termination")
        )
        self.format_response = format_response

    def _as_str(self, value: str | bytes, name: str) -> str:
        if isinstance(value, bytes):
            return value.decode(self.encoding)
        if isinstance(value, str):
            return value
        raise ValueError(f"{name} must be str or bytes, not {type(value).__name__}")

    def set_termination(
        self,
        termination: str | bytes,
        receive_termination: str | bytes | None = None,
    ) -> None:
        """
        Change the terminations

        Called through ProtocolEngine.configure, which runs it on the reactor thread and
        then applies the new stop_conditions to the adapter
        """
        self.termination = self._as_str(termination, "termination")
        self.receive_termination = (
            self.termination
            if receive_termination is None
            else self._as_str(receive_termination, "receive_termination")
        )

    def encode(self, payload: str) -> list[bytes]:
        return [(payload + self.termination).encode(self.encoding)]

    def decode(self, data: bytes) -> str:
        """Turn the bytes of one frame into a payload, no I/O and no state"""
        text = data.decode(self.encoding)
        if self.format_response and text.endswith(self.receive_termination):
            return text[: -len(self.receive_termination)]
        return text

    def push(self, frame: AdapterReadFrame[bytes]) -> BackendOutput[bytes, str]:
        return BackendOutput(payloads=[self.decode(frame.data)])

    @property
    def stop_conditions(self) -> list[StopCondition] | None:
        # A new instance on every call : a stop-condition holds the state of the frame
        # being assembled and must not be shared
        return [Termination(self.receive_termination.encode(self.encoding))]

    @property
    def default_timeout(self) -> TimeoutType:
        return 2.0


class Delimited(Protocol[DelimitedBackend, bytes, str]):
    """
    Text protocol, every command ends with a termination, LF by default

    Parameters
    ----------
    adapter : Adapter
        Its stop-conditions are replaced by Termination(receive_termination)
    termination : str or bytes
        Appended to every payload written, '\\n' by default
    format_response : bool
        Remove the termination from the payloads read, True by default
    encoding : str
    timeout : float, None or ...
        Time to wait for a complete payload, 2 s by default
    receive_termination : str, bytes or None
        Termination of the frames received, the value of termination if None
    alias : str
    """

    def __init__(
        self,
        adapter: Adapter[Any, bytes],
        termination: str | bytes = "\n",
        *,
        format_response: bool = True,
        encoding: str = "utf-8",
        timeout: TimeoutParameterType = ...,
        receive_termination: str | bytes | None = None,
        alias: str = "",
    ) -> None:
        super().__init__(
            adapter,
            DelimitedBackend(
                termination=termination,
                receive_termination=receive_termination,
                encoding=encoding,
                format_response=format_response,
            ),
            timeout,
            alias,
        )

    @property
    def termination(self) -> str:
        """Termination appended to every payload written"""
        return self._backend.termination

    @property
    def receive_termination(self) -> str:
        """Termination of the frames received"""
        return self._backend.receive_termination

    def set_termination(
        self,
        termination: str | bytes,
        receive_termination: str | bytes | None = None,
    ) -> None:
        """
        Set the terminations, receive_termination is termination if None

        The stop-conditions of the adapter follow
        """
        self._engine.configure(
            lambda backend: backend.set_termination(termination, receive_termination)
        ).result()


class AsyncDelimited(AsyncProtocol[DelimitedBackend, bytes, str]):
    """
    Async text protocol, same parameters as Delimited
    """

    def __init__(
        self,
        adapter: AsyncAdapter[Any, bytes],
        termination: str | bytes = "\n",
        *,
        format_response: bool = True,
        encoding: str = "utf-8",
        timeout: TimeoutParameterType = ...,
        receive_termination: str | bytes | None = None,
        alias: str = "",
    ) -> None:
        super().__init__(
            adapter,
            DelimitedBackend(
                termination=termination,
                receive_termination=receive_termination,
                encoding=encoding,
                format_response=format_response,
            ),
            timeout,
            alias,
        )

    @property
    def termination(self) -> str:
        """Termination appended to every payload written"""
        return self._backend.termination

    @property
    def receive_termination(self) -> str:
        """Termination of the frames received"""
        return self._backend.receive_termination

    async def set_termination(
        self,
        termination: str | bytes,
        receive_termination: str | bytes | None = None,
    ) -> None:
        """
        Set the terminations, receive_termination is termination if None

        The stop-conditions of the adapter follow
        """
        await asyncio.wrap_future(
            self._engine.configure(
                lambda backend: backend.set_termination(
                    termination, receive_termination
                )
            )
        )
