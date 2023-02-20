# Sébastien Deriaz
# 17.02.2023
# descriptors.py
#
# Classes to describe the address of a device with multiple protocols

class Descriptor:
    pass


class IP(Descriptor):
    def __init__(self, str):
        pass

class Serial(Descriptor):
    def __init__(self, str):
        pass

class USB(Descriptor):
    def __init__(self, VID, PID):
        pass

class VISA(Descriptor): # not sure about this one
    def __init__(self):
        pass

class SyndesiID(Descriptor):
    def __init__(self, desc, type):
        """
        Finds the device corresponding to
        a unique Syndesi ID (syndesi devices only)

        Parameters
        ----------
        desc : str
            ID descriptor
        type : ?
            Connection type (Ethernet, Serial, etc...)
        """
        pass


def auto(str):
    """
    Automatically decide which descriptor class should be used
    for the given string description
    """
    pass