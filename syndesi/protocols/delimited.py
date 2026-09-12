# File : delimited.py
# Author : Sébastien Deriaz
# License : GPL
"""
Delimited protocol, for devices exchanging text commands ended by a delimiter
(\\n, \\r, \\r\\n, ...)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from ..adapters.adapter import Adapter, AsyncAdapter
from ..adapters.stop_conditions import StopCondition, Termination
from ..adapters.utils import TimeoutParameterType, TimeoutType
from .protocol import AsyncProtocol, Codec, Protocol


@dataclass(frozen=True)
class DelimitedCodec(Codec[bytes, str]):
    """
    Text commands ended by a termination

    Parameters
    ----------
    termination : str
        Appended to every payload written
    receive_termination : str
        Ends every frame received
    encoding : str
    format_response : bool
        Remove receive_termination from the payloads read
    """

    termination: str
    receive_termination: str
    encoding: str
    format_response: bool

    def __str__(self) -> str:
        if self.receive_termination == self.termination:
            return repr(self.termination)
        return f"{self.termination!r}/{self.receive_termination!r}"

    @property
    def default_timeout(self) -> TimeoutType:
        return 2.0

    @property
    def stop_conditions(self) -> list[StopCondition]:
        # A new one on every call, a stop-condition holds the state of the frame being read
        return [Termination(self.receive_termination.encode(self.encoding))]

    def encode(self, payload: str) -> bytes:
        return (payload + self.termination).encode(self.encoding)

    def decode(self, data: bytes) -> str:
        text = data.decode(self.encoding)
        if self.format_response and text.endswith(self.receive_termination):
            return text[: -len(self.receive_termination)]
        return text

def _as_str(value: str | bytes, encoding: str, name: str) -> str:
    if isinstance(value, bytes):
        return value.decode(encoding)
    if isinstance(value, str):
        return value
    raise ValueError(f"{name} must be str or bytes, not {type(value).__name__}")

def _delimited_codec(
    termination: str | bytes,
    receive_termination: str | bytes | None,
    encoding: str,
    format_response: bool,
) -> DelimitedCodec:
    send = _as_str(termination, encoding, "termination")
    return DelimitedCodec(
        termination=send,
        receive_termination=(
            send
            if receive_termination is None
            else _as_str(receive_termination, encoding, "receive_termination")
        ),
        encoding=encoding,
        format_response=format_response,
    )

class Delimited(Protocol[bytes, str]):
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
        ``...`` keeps the adapter timeout if it was given one, 2 s otherwise
    receive_termination : str, bytes or None
        Termination of the frames received, the value of termination if None
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
    ) -> None:
        super().__init__(
            adapter,
            _delimited_codec(termination, receive_termination, encoding, format_response),
            timeout=timeout,
        )

    @property
    def codec(self) -> DelimitedCodec:
        """Codec of the protocol"""
        return cast(DelimitedCodec, super().codec)

    @property
    def termination(self) -> str:
        """Termination appended to every payload written"""
        return self.codec.termination

    @property
    def receive_termination(self) -> str:
        """Termination of the frames received"""
        return self.codec.receive_termination

    def set_termination(
        self, termination: str | bytes, receive_termination: str | bytes | None = None
    ) -> None:
        """Set the terminations, receive_termination is termination if None"""
        codec = self.codec
        self._set_codec(
            _delimited_codec(
                termination, receive_termination, codec.encoding, codec.format_response
            )
        )


class AsyncDelimited(AsyncProtocol[bytes, str]):
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
    ) -> None:
        super().__init__(
            adapter,
            _delimited_codec(termination, receive_termination, encoding, format_response),
            timeout=timeout,
        )

    @property
    def codec(self) -> DelimitedCodec:
        """Codec of the protocol"""
        return cast(DelimitedCodec, super().codec)

    @property
    def termination(self) -> str:
        """Termination appended to every payload written"""
        return self.codec.termination

    @property
    def receive_termination(self) -> str:
        """Termination of the frames received"""
        return self.codec.receive_termination

    async def set_termination(
        self, termination: str | bytes, receive_termination: str | bytes | None = None
    ) -> None:
        """Set the terminations, receive_termination is termination if None"""
        codec = self.codec
        await self._set_codec(
            _delimited_codec(
                termination, receive_termination, codec.encoding, codec.format_response
            )
        )
