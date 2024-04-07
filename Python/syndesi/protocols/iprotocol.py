from ..adapters import Adapter

class IProtocol:
    def __init__(self, adapter : Adapter) -> None:
        self._adapter = adapter

    def write(self, data):
        pass

    def query(self, data):
        pass

    def read(self):
        pass