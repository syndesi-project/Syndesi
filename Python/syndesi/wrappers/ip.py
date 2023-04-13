# Sébastien Deriaz
# 20.02.2023
# IP.py
#
# The IP class is a wrapper for all TCP/UDP communications
from .wrapper import Wrapper
from enum import Enum


class Status(Enum):
    DISCONNECTED = 0
    CONNECTED = 1



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
        pass

    def open(self):
        pass

    def close(self):
        pass
            
    def write(self, data : bytearray):
        pass

    def read(self):
        pass