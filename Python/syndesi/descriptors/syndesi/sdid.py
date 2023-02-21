# Syndesi ID
#
# Sébastien Deriaz
# 14.11.2022
from enum import Enum

class AddressType(Enum):
        NONE = 0
        IPV4 = 1
        IPV6 = 2

class SyndesiID:
    def __init__(self, addressType : AddressType):
        """
        Syndesi ID instance

        Parameters
        ----------

        """
        self.addressType = addressType