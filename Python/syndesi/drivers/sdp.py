from ..wrappers.wrapper import Wrapper
from .base import Device

class SDPDevice(Device):
    def __init__(self, wrapper : Wrapper):
        """
        SDP (Syndesi Device Protocol) compatible device

        Parameters
        ----------
        wrapper : Wrapper
        """
        self._wrapper = wrapper