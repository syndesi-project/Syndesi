from ..adapters import Adapter
from ..adapters import Timeout
from ..adapters.auto import auto_adapter
import logging
from ..tools.log import LoggerAlias



class HSMS:
    def __init__(self, adapter : Adapter, timeout : Timeout = ...) -> None:
        self._adapter = auto_adapter(adapter)
        if timeout != ...:
            self._adapter.set_default_timeout(timeout)
        self._logger = logging.getLogger(LoggerAlias.PROTOCOL.value)

    def flushRead(self):
        self._adapter.flushRead()

    def send(self, data):
        # Message format :
        #   Length : 4 bytes
        #   Header : 
        #
        pass

    def query(self, data, timeout : Timeout = ...):
        pass

    def read(self):
        pass