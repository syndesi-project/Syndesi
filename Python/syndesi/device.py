# Syndsi Device class
#
# Sébastien Deriaz
# 14.11.2022
from .payload import Payload
from .network import network
from .frame import OutboundFrame, InboundFrame
from .sdid import SyndesiID, AddressType

class Device:
    def __init__(self, descriptor):
        """
        New device instance
        """


    def send(self, payload : Payload):
        
        ID = SyndesiID(AddressType.IPV4)

        frame = OutboundFrame(payload, ID)

        outputFrame = network.request(frame)

        return outputFrame.payload