# File : scpi.py
# Author : Sébastien Deriaz
# License : GPL
"""
SCPI Protocol, formats data as command-like (similar to Delimited) and
provides extra functionalities

"""

from types import EllipsisType

from ..adapters.bytesadapter import BytesAdapter
from ..adapters.ip import IP
from ..adapters.timeout import Timeout
from .delimited import Delimited


class SCPI(Delimited):
    """
    SCPI Protocol layer

    Parameters
    ----------
    adapter : Adapter
    termination : str
        '\n' by default
    receive_termination : str
        A custom different termination when receiving datas.
        
        None by default (copy value from termination)
    timeout : Timeout/float/tuple
        Set device timeout
    """

    DEFAULT_PORT = 5025

    def __init__(
        self,
        adapter: BytesAdapter,
        termination: str = "\n",
        receive_termination: str | None = None,
        *,
        timeout: Timeout | None | EllipsisType = ...,
        encoding: str = "utf-8",
    ) -> None:

        # Configure the adapter for stop-condition mode (timeouts will raise errors)
        if not adapter._is_default_stop_condition:
            raise ValueError(
                "No stop-conditions can be set for an adapter used by SCPI protocol"
            )

        # adapter.set_timeout(self.timeout)
        if isinstance(adapter, IP):
            adapter.set_default_port(self.DEFAULT_PORT)
        # Give the adapter to the Protocol base class
        super().__init__(
            adapter=adapter,
            termination=termination,
            format_response=True,
            encoding=encoding,
            timeout=timeout,
            receive_termination=receive_termination,
        )

    def _default_timeout(self) -> Timeout | None:
        return Timeout(response=5)

    def write_raw(self, data: bytes, termination: bool = False) -> None:
        """
        Write raw data to the device

        Parameters
        ----------
        data : bytes
        termination : bool
            Add termination to the data, False by default
        """
        self._adapter.write(
            data + (self._termination.encode(self._encoding) if termination else b"")
        )
