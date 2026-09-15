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

from syndesi.adapters.engine import Engine

from ..adapters.adapter import Adapter, AsyncAdapter
from ..adapters.stop_conditions import StopCondition, Termination
from ..adapters.utils import TimeoutParameterType, TimeoutType
from .protocol import AsyncProtocol, Protocol, ProtocolEngine

class DelimitedEngine(ProtocolEngine[bytes, str]):
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

    def __init__(self,
                 adapter_engine: Engine[Any, bytes],
                 termination : str,
                 receive_termination : str | None) -> None:
        super().__init__(adapter_engine)


# #@dataclass
# class DelimitedCodec(Codec[bytes, str]):

#     def __init__(self,
#                 termination: str | bytes,
#                 receive_termination: str | bytes | None,
#                 encoding: str,
#                 format_response: bool
#         ) -> None:

        
#         self.termination = self._as_str(termination, encoding, "termination")
#         self.receive_termination = (
#             self.termination if receive_termination is None
#             else self._as_str(receive_termination, encoding, "receive_termination")
#         )
#         self.encoding = encoding
#         self.format_response = format_response

#     def __str__(self) -> str:
#         if self.receive_termination == self.termination:
#             return repr(self.termination)
#         return f"{self.termination!r}/{self.receive_termination!r}"

#     @property
#     def default_timeout(self) -> TimeoutType:
#         return 2.0

#     @property
#     def stop_conditions(self) -> list[StopCondition]:
#         # A new one on every call, a stop-condition holds the state of the frame being read
#         return [Termination(self.receive_termination.encode(self.encoding))]

#     def encode(self, payload: str) -> bytes:
#         return (payload + self.termination).encode(self.encoding)

#     def decode(self, data: bytes) -> str:
#         text = data.decode(self.encoding)
#         if self.format_response and text.endswith(self.receive_termination):
#             return text[: -len(self.receive_termination)]
#         return text

#     def _as_str(self, value: str | bytes, encoding: str, name: str) -> str:
#         if isinstance(value, bytes):
#             return value.decode(encoding)
#         if isinstance(value, str):
#             return value
#         raise ValueError(f"{name} must be str or bytes, not {type(value).__name__}")

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
        super().__init__(DelimitedEngine(
            adapter.engine,
            termination=termination,
            receive_termination=receive_termination
        ))

        self._engine

    @property
    def termination(self) -> str:
        """Termination appended to every payload written"""
        #return self._engine.termi
        return self._engine

    @property
    def receive_termination(self) -> str:
        """Termination of the frames received"""
        return self.codec.receive_termination

    # def set_termination(
    #     self, termination: str | bytes, receive_termination: str | bytes | None = None
    # ) -> None:
    #     """Set the terminations, receive_termination is termination if None"""
    #     codec = self.codec
    #     self._set_codec(
    #         DelimitedCodec(

    #         )
    #         _delimited_codec(
    #             termination, receive_termination, codec.encoding, codec.format_response
    #         )
    #     )

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
            DelimitedEngine(
                adapter.engine,
                termination=termination,
                receive_termination=receive_termination,
                encoding=encoding,
                format_response=format_response
            )
        )

    # @property
    # def codec(self) -> DelimitedCodec:
    #     """Codec of the protocol"""
    #     return cast(DelimitedCodec, super().codec)

    @property
    def termination(self) -> str:
        """Termination appended to every payload written"""
        return self.codec.termination

    @property
    def receive_termination(self) -> str:
        """Termination of the frames received"""
        return self.codec.receive_termination

    # async def set_termination(
    #     self, termination: str | bytes, receive_termination: str | bytes | None = None
    # ) -> None:
    #     """Set the terminations, receive_termination is termination if None"""
    #     codec = self.codec
    #     await self._set_codec(
    #         DelimitedCodec(
    #             termination=termination,
    #             receive_termination=receive_termination,
    #             codec.enco
    #         _delimited_codec(
    #             termination, receive_termination, codec.encoding, codec.format_response
    #         )
    #     )
