from ..wrappers.wrapper import Wrapper


class Device:
    
    def __init__(self, wrapper : Wrapper):
        """
        A Device doesn't implement any session protocol,
        it can only be used to transmit/receive
        raw data with the approriate wrapper

        Parameters
        ----------
        wrapper : Wrapper
        """
        self._wrapper = wrapper


syndesi communication protocol

syndesi protocol