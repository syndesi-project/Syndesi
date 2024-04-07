from ..adapters import Adapter
from .iprotocol import IProtocol


class SDP(IProtocol):
    def __init__(self, adapter: Adapter) -> None:
        """
        SDP (Syndesi Device Protocol) compatible device

        Parameters
        ----------
        wrapper : Wrapper
        """
        super().__init__(adapter)