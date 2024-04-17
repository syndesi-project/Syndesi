from ..adapters import Adapter

class Protocol:
    def __init__(self, adapter : Adapter, timeout) -> None:
        self._adapter = adapter

    def write(self, data):
        pass

    def query(self, data):
        pass

    def read(self):
        pass