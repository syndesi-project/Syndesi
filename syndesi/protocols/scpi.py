# File : scpi.py
# Author : Sébastien Deriaz
# License : GPL
"""
SCPI Protocol, formats data as command-like (similar to Delimited) and
provides extra functionalities

"""

from types import EllipsisType

from ..adapters.adapter import Adapter
from ..adapters.ip import IP
from ..adapters.timeout import Timeout, TimeoutAction
from .delimited import Delimited


class SCPI(Delimited):
    """
    SCPI Protocol layer

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

    DEFAULT_PORT = 5025

    def __init__(
        self,
        adapter: Adapter,
        send_termination: str = "\n",
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
            termination=send_termination,
            format_response=True,
            encoding=encoding,
            timeout=timeout,
            receive_termination=receive_termination,
        )

        # Connect the adapter if it wasn't done already
        # self._adapter.connect()

    def _default_timeout(self) -> Timeout | None:
        return Timeout(response=5, action=TimeoutAction.ERROR.value)

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

    # def read_raw(
    #     self,
    #     timeout: Timeout | None | EllipsisType = ...,
    #     stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    # ) -> bytes:
    #     """
    #     Blocking read and return bytes data

    #     Parameters
    #     ----------
    #     timeout : Timeout
    #         Optional temporary timeout
    #     stop_conditions : [StopCondition]
    #         Optional temporary stop-conditions

    #     Returns
    #     -------
    #     data : bytes
    #     """
    #     signal = self.read_detailed(
    #         timeout=timeout,
    #         stop_conditions=stop_conditions,
    #     )
    #     return signal.data()
