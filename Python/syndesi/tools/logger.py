# logger.py
# Sébastien Deriaz
# 11.03.2024
#
# A class to manage adapter logging
from enum import Enum, IntEnum
from typing import Union
from dataclasses import dataclass
from time import time

class EntryType(Enum):
    DATA_WRITE = 0
    DATA_READ = 1
    STATUS = 2

class LogLevel(IntEnum):
    BASIC = 0 # Status, open/close, errors, etc...
    DETAILED = 1 # Data
    COMPLETE = 2 # All, data fragments, timeouts, stop conditions, etc...

@dataclass
class Entry:
    _type : EntryType
    timestamp : float
    data : bytes | str
    level : LogLevel

class LoggerClientType:
    ADAPTER = 'adapter'
    PROTOCOL = 'protocol'
    DRIVER = 'driver'


# Store (timestamp, type, data) tuples in the GlobalLogger
# The type indicates what kind of entry it is (data send, data receive, information, etc...) 

# The Logger (or one of its children) takes care of "high-level" logging functions like "log_adapter_open" or "log_adapter_data_out"


class GlobalLogger:
    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(GlobalLogger, cls).__new__(cls)
            cls.instance._log = {}
            cls.instance._properties = {}
        return cls.instance
            
    def log(self, identifier : int, entry : Entry):
        if identifier not in self._log:
            self._log[identifier] = []
        self._log[identifier].append(entry)

    def register_properties(self, identifier : int, values : dict):
        if identifier not in self._properties:
            self._properties[identifier] = {}
        self._properties[identifier].update(values)

class Logger:
    def __init__(self, client_type : str) -> None:
        """
        Logger class to store actions of syndesi adapters, protocols and/or drivers
        
        Parameters
        ----------
        client_type : str
            'adapter', 'protocol' or 'driver'

        """
        self._global_logger = GlobalLogger()
        self._client_type = client_type
        self._level = LogLevel.BASIC
    
    def set_log_level(self, level : int):
        self._level = LogLevel(level)

    def _log(self, entry : Entry):
        self._global_logger.log(id(self), entry)

    def register_properties(self, values : dict):
        self._global_logger.log(id(self), values)

    def log_status(self, message : str, level : int):
        """
        Log status change of device (opening, closing, setting parameters, etc...)

        Parameters
        ----------
        message : str
        level : int
            0 : basic
            1 : detailed
            2 : complete
        """
        if self._level >= LogLevel(level):
            self._log(Entry(EntryType.STATUS, time(), message, level))

class AdapterLogger(Logger):
    def __init__(self, keywords : dict) -> None:
        super().__init__('adapter')
    
    def log_read(self, output_data, previous_read_buffer):
        pass

    def log_write(self, data):
        pass

class ProtocolLogger(Logger):
    def __init__(self, keywords : dict) -> None:
        super().__init__('protocol')

class DriverLogger(Logger):
    def __init__(self, keywords : dict) -> None:
        super().__init__('driver')