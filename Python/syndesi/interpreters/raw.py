# Raw interpreter
#
# Sébastien Deriaz
# 18.11.2022

from ..payload import Payload

class Reply(Payload):
    def __init__(self, buffer):
        """
        Reply request

        Fields : 
            - data : bytearray
        """
        self.data = b''
        self.parse(buffer)

    def value(self):
        return self.data
        
    def parse(self, payload):
        self.data = payload

class Request(Payload):
    def __init__(self):
        """
        Payload request

        Fields : 
            - data : bytearray
        """
        self._reply = Reply
        self.data = b''

    def value(self):
        return self.data
        
    def parse(self, payload):
        data = payload



