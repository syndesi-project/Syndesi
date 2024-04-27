from ..adapters import Adapter, Timeout
from .protocol import Protocol


# Raw protocols provide the user with the binary data directly,
# without converting it to string first

class Raw(Protocol):
    def __init__(self, adapter: Adapter, timeout : Timeout = None) -> None:
        """
        Raw device, no presentation and application layers

        Parameters
        ----------
        adapter : IAdapter
        """
        super().__init__(adapter, timeout)

    def write(self, data : bytes):
        self._adapter.write(data)

    def query(self, data : bytes, timeout=None, stop_condition=None, return_metrics : bool = False) -> bytes:
        self._adapter.flushRead()
        self.write(data)
        return self.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)

    def read(self, timeout=None, stop_condition=None, return_metrics : bool = False) -> bytes:
        return self._adapter.read(timeout=timeout, stop_condition=stop_condition, return_metrics=return_metrics)