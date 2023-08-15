# adapters.py
# Sébastien Deriaz
# 06.05.2023
#
# Adapters provide a common abstraction for the media layers (physical + data link + network)
# The following classes are provided, which all are derived from the main Adapter class 
#   - IP
#   - Serial
#   - VISA
# 
# Note that technically VISA is not part of the media layer, only USB is.
# This is a limitation as it is to this day not possible to communication "raw"
# with a device through USB yet
#
#
#
#
# Timeout system
# We can differentiate two kinds of timeout :
#   - transmission timeout (aka "timeout"): the time it takes for a device to start transmitting what we expect
#   - continuation timeout : the time it takes for a device to continue sending the requested data

from abc import abstractmethod, ABC

class IAdapter(ABC):
    @abstractmethod
    def __init__(self, descriptor, *args):
        pass

    @abstractmethod
    def flushRead(self):
        """
        Flush the input buffer
        """
        pass

    @abstractmethod
    def open(self):
        """
        Start communication with the device
        """
        pass

    @abstractmethod
    def close(self):
        """
        Stop communication with the device
        """
        pass
            
    @abstractmethod
    def write(self, data : bytearray):
        """
        Send data to the device
        """
        pass
    
    @abstractmethod
    def read(self, timeout=None, continuation_timeout=None, until_char=None) -> bytearray:
        """
        Read data from the device
        """
        pass

    @abstractmethod
    def query(self, data : bytearray, timeout=None, continuation_timeout=None) -> bytearray:
        """
        Shortcut function that combines
        - flush_read
        - write
        - read
        """
        pass