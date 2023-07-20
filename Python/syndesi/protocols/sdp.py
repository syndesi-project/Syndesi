from ..adapters import IAdapter
from .iprotocol import IProtocol


class SDP(IProtocol):
    def __init__(self, adapter: IAdapter) -> None:
        """
        SDP (Syndesi Device Protocol) compatible device

        Parameters
        ----------
        wrapper : Wrapper
        """
        super().__init__(adapter)