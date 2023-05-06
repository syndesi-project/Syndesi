from .protocol import Primary
from ...wrappers.wrapper import Wrapper


class Raw(Primary):
    def __init__(self, wrapper : Wrapper):
        """
        Raw device, no presentation and application protocol


        Parameters
        ----------
        wrapper : Wrapper
        """
        self._wrapper = wrapper