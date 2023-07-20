from ..adapters import IAdapter

class IProtocol:
    def __init__(self, adapter : IAdapter) -> None:
        self._adapter = adapter