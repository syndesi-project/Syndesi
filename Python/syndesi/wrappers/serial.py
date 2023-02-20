# Sébastien Deriaz
# 20.02.2023
from .wrapper import Wrapper


class Serial(Wrapper):
    def __init__(self, descriptor : str):
        """
        Serial communication wrapper

        Parameters
        ----------
        descriptor : str
            Serial port (COMx or ttyACMx)
        """
        pass

