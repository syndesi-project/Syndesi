# File : protocol.py
# Author : Sébastien Deriaz
# License : GPL
"""
Protocol base class. A protocol applies format of outgoing data and removes format
of incoming data
"""

import logging
from abc import abstractmethod
from collections.abc import Callable
from types import EllipsisType
from typing import Any

from syndesi.adapters.stop_condition import StopCondition

from ..adapters.adapter import Adapter
from ..adapters.auto import auto_adapter
from ..adapters.backend.adapter_backend import AdapterReadPayload, AdapterSignal

# from syndesi.adapters.stop_condition import StopCondition
from ..adapters.timeout import Timeout
from ..tools.log_settings import LoggerAlias


class Protocol:
    """
    Protocol base class    
    """
    def __init__(
        self,
        adapter: Adapter,
        timeout: Timeout | None | EllipsisType = ...,
        event_callback: Callable[[AdapterSignal], None] | None = None,
    ) -> None:
        # TODO : Convert the callable from AdapterSignal to ProtocolSignal or something similar
        self._adapter = auto_adapter(adapter)

        self._event_callback = event_callback
        self._adapter.set_event_callback(self._on_event)

        if timeout is not ...:
            self._adapter.set_default_timeout(timeout)
        self._logger = logging.getLogger(LoggerAlias.PROTOCOL.value)

        if timeout is ...:
            self._adapter.set_timeout(self._default_timeout())
        else:
            self._adapter.set_timeout(timeout)

    @abstractmethod
    def _default_timeout(self) -> Timeout | None:
        pass

    def _on_event(self, event: AdapterSignal) -> None:
        if self._event_callback is not None:
            self._event_callback(event)

    @abstractmethod
    def _on_data_ready_event(self, data: AdapterReadPayload) -> None:
        pass

    def flush_read(self) -> None:
        """
        Clear read buffer
        """
        self._adapter.flush_read()

    @abstractmethod
    def write(self, payload: Any) -> None:
        """
        Write payload to the device
        """

    def open(self) -> None:
        """
        Open the adapter
        """
        self._adapter.open()

    def try_open(self) -> bool:
        """
        Try to open the adapter, return True on success
        """
        return self._adapter.try_open()

    def is_opened(self) -> bool:
        """
        Return True if the adapter is opened
        """
        return self._adapter.is_opened()

    def close(self) -> None:
        """
        Close the protocol and adapter
        """
        self._adapter.close()

    @abstractmethod
    def query(
        self,
        payload: Any,
        timeout: Timeout | None | EllipsisType,
        stop_conditions : StopCondition | EllipsisType | list[StopCondition]
    ) -> Any:
        """
        Blocking query (write + read) and return payload
        """

    @abstractmethod
    def read(self,
             timeout : Timeout | None | EllipsisType,
             stop_conditions : StopCondition | EllipsisType | list[StopCondition]) -> Any:
        """
        Blocking read
        """

    @abstractmethod
    def query_detailed(self,
                    payload : Any,
                    timeout : Timeout | None | EllipsisType,
                    stop_conditions : StopCondition | EllipsisType | list[StopCondition]) -> Any:
        """
        Blocking query (write + read) and return adapter signal
        """

    def read_detailed(
        self,
        timeout: Timeout | None | EllipsisType = ...,
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
    ) -> AdapterReadPayload:
        """
        Blocking read and return full payload (AdapterReadPayload class)

        Parameters
        ----------
        timeout : Timeout
            Optional temporary timeout
        stop_conditions : [StopCondition]
            Optional temporary stop-conditions

        Returns
        -------
        signal : AdapterReadPayload
        """
        return self._adapter.read_detailed(
            timeout=timeout, stop_conditions=stop_conditions
        )
