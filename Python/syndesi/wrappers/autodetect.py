# Sébastien Deriaz
# 20.02.2023


from .wrapper import Wrapper
from .ip import IP
from .serial import Serial


def wrapperAutoDetect(*args) -> Wrapper:
    """
    Detect and return the corresponding wrapper for the given descriptor (or multiple)
    """

    # TODO : Implement

    return IP(args[0])
    
