# Sébastien Deriaz
# 20.02.2023
# IP.py
#
# The IP class is a wrapper for all TCP/UDP communications
from .wrapper import Wrapper

class IP(Wrapper):
    def __init__(self, descriptor : str, port = None):
        """
        IP stack wrapper

        Parameters
        ----------
        descriptor : str
            IP description
        port : int
            port used (optional, can be specified in descriptor)
        """
