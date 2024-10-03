from ..adapters import Adapter
from ..adapters import Timeout
from ..adapters.auto import auto_adapter
import logging
from ..tools.log import LoggerAlias

class Protocol:
    def __init__(self, adapter : Adapter, timeout : Timeout) -> None:
        self._adapter = auto_adapter(adapter)
        self._adapter.set_default_timeout(timeout)
        self._logger = logging.getLogger(LoggerAlias.PROTOCOL.value)

    def flushRead(self):
        self._adapter.flushRead()

    def write(self, data):
        pass

    def query(self, data):
        pass

    def read(self):
        pass