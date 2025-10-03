# File : visa.py
# Author : Sébastien Deriaz
# License : GPL
#
# VISA adatper, uses a VISA backend like pyvisa-py or NI to communicate with instruments

from collections.abc import Callable
from types import EllipsisType

from syndesi.adapters.backend.adapter_backend import AdapterSignal
from syndesi.adapters.stop_condition import StopCondition

from .adapter import Adapter
from .backend.descriptors import VisaDescriptor
from .timeout import Timeout


class Visa(Adapter):
    def __init__(
        self,
        descriptor: str,
        alias: str = "",
        stop_conditions: StopCondition | EllipsisType | list[StopCondition] = ...,
        timeout: None | float | Timeout | EllipsisType = ...,
        encoding: str = "utf-8",
        event_callback: Callable[[AdapterSignal], None] | None = None,
        backend_address: str | None = None,
        backend_port: int | None = None,
    ) -> None:
        super().__init__(
            VisaDescriptor.from_string(descriptor),
            alias=alias,
            stop_conditions=stop_conditions,
            timeout=timeout,
            encoding=encoding,
            event_callback=event_callback,
            backend_address=backend_address,
            backend_port=backend_port,
        )

        self._logger.info("Setting up VISA IP adapter")

    def _default_timeout(self) -> Timeout:
        return Timeout(response=5, action="error")
