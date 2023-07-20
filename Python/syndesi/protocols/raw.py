from ..adapters import IAdapter
from .iprotocol import IProtocol

class Raw(IProtocol):
    def __init__(self, adapter: IAdapter) -> None:
        """
        Raw device, no presentation and application layers

        Parameters
        ----------
        adapter : IAdapter
        """
        super().__init__(adapter)

    def write(self, data : bytearray):
        self._adapter.write(data)

    def query(self, data : bytearray) -> bytearray:
        self._adapter.flushRead()
        self.write(data)
        return self.read()

    def read(self) -> bytearray:
        return self._adapter.read()