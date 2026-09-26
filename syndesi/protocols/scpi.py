# File : scpi.py
# Author : Sébastien Deriaz
# License : GPL
"""
SCPI protocol, text commands like Delimited plus the SCPI specifics
(well known port, longer default timeout, raw writes)
"""

from __future__ import annotations

from typing import Any

from ..adapters.adapter import Adapter, AsyncAdapter
from ..adapters.ip import IP, AsyncIP
from ..adapters.utils import TimeoutParameterType, TimeoutType
from .delimited import DelimitedBackend
from .protocol import AsyncProtocol, Protocol

SCPI_DEFAULT_PORT = 5025


class SCPIBackend(DelimitedBackend):
    """
    Delimited, with the SCPI defaults

    A backend composing another one : SCPI is Delimited plus a few conventions, so
    there is nothing to re-encode or re-assemble here
    """

    @property
    def default_timeout(self) -> TimeoutType:
        # Instruments can be slow to answer a measurement query
        return 5.0


def _check_adapter(adapter: Adapter[Any, bytes] | AsyncAdapter[Any, bytes]) -> None:
    """
    SCPI decides the framing (the termination), so the adapter must not have its own
    """
    if not adapter.has_default_stop_conditions:
        raise ValueError(
            "No stop-conditions can be set on an adapter used by the SCPI protocol,"
            " SCPI sets them from its termination"
        )


class SCPI(Protocol[SCPIBackend, bytes, str]):
    """
    SCPI protocol

    Parameters
    ----------
    adapter : Adapter
        Its port defaults to 5025 and its stop-conditions to Termination(termination)
    termination : str or bytes
        Appended to every command written, '\\n' by default
    receive_termination : str, bytes or None
        Termination of the responses, the value of termination if None
    timeout : float, None or ...
        Time to wait for a complete response, 5 s by default
    encoding : str
    alias : str
    """

    DEFAULT_PORT = SCPI_DEFAULT_PORT

    def __init__(
        self,
        adapter: Adapter[Any, bytes],
        termination: str | bytes = "\n",
        receive_termination: str | bytes | None = None,
        *,
        timeout: TimeoutParameterType = ...,
        encoding: str = "utf-8",
        alias: str = "",
    ) -> None:
        _check_adapter(adapter)
        if isinstance(adapter, IP):
            adapter.set_default_port(self.DEFAULT_PORT)

        super().__init__(
            adapter,
            SCPIBackend(
                termination=termination,
                receive_termination=receive_termination,
                encoding=encoding,
                format_response=True,
            ),
            timeout,
            alias,
        )

    @property
    def termination(self) -> str:
        """Termination appended to every command written"""
        return self._backend.termination

    def write_raw(self, data: bytes, termination: bool = False) -> None:
        """
        Write bytes to the device without encoding them

        Parameters
        ----------
        data : bytes
        termination : bool
            Append the termination to the data, False by default
        """
        if termination:
            data += self._backend.termination.encode(self._backend.encoding)
        super().write_raw(data)


class AsyncSCPI(AsyncProtocol[SCPIBackend, bytes, str]):
    """
    Async SCPI protocol, same parameters as SCPI
    """

    DEFAULT_PORT = SCPI_DEFAULT_PORT

    def __init__(
        self,
        adapter: AsyncAdapter[Any, bytes],
        termination: str | bytes = "\n",
        receive_termination: str | bytes | None = None,
        *,
        timeout: TimeoutParameterType = ...,
        encoding: str = "utf-8",
        alias: str = "",
    ) -> None:
        _check_adapter(adapter)
        if isinstance(adapter, AsyncIP):
            adapter.set_default_port(self.DEFAULT_PORT)

        super().__init__(
            adapter,
            SCPIBackend(
                termination=termination,
                receive_termination=receive_termination,
                encoding=encoding,
                format_response=True,
            ),
            timeout,
            alias,
        )

    @property
    def termination(self) -> str:
        """Termination appended to every command written"""
        return self._backend.termination

    async def write_raw(self, data: bytes, termination: bool = False) -> None:
        """
        Write bytes to the device without encoding them

        Parameters
        ----------
        data : bytes
        termination : bool
            Append the termination to the data, False by default
        """
        if termination:
            data += self._backend.termination.encode(self._backend.encoding)
        await super().write_raw(data)
