from ..adapters import Adapter
from .protocol import Protocol


class SDP(Protocol):
    def __init__(self, adapter: Adapter) -> None:
        """
        SDP (Syndesi Device Protocol) compatible device

        Parameters
        ----------
        wrapper : Wrapper
        """
        super().__init__(adapter)