from ..adapters import Adapter
from ..adapters import Timeout

class Protocol:
    def __init__(self, adapter : Adapter, timeout : Timeout) -> None:
        self._adapter = adapter
        self._adapter.set_default_timeout(timeout)

    def write(self, data):
        pass

    def query(self, data):
        pass

    def read(self):
        pass