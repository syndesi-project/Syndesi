from ..adapters import IAdapter

class IProtocol:
    def __init__(self, adapter : IAdapter) -> None:
        self._adapter = adapter

    def write(self, data):
        pass

    def query(self, data):
        pass

    def read(self):
        pass