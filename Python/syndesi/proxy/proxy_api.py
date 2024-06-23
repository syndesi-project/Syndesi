# proxy_api.py
# Sébastien Deriaz
# 29.05.2024

import sys
from dataclasses import dataclass

from ..api.api import APICall, ACTION_ATTRIBUTE, register_api, APIItem

class ProxyException(Exception):
    pass

# IP specific
@dataclass
class IPInstanciate(APICall):
    action = 'ip_adapter_inst'
    address : str
    port : int
    transport : str
    buffer_size : int

@dataclass
class TimeoutAPI(APIItem):
    name = 'timeout'
    response : float
    continuation : float
    total : float
    on_response : str
    on_continuation : str
    on_total : str

@dataclass
class StopConditionAPI(APIItem):
    pass

@dataclass
class TerminationAPI(StopConditionAPI):
    name = 'termination'
    sequence : bytes

@dataclass
class LengthAPI(StopConditionAPI):
    name = 'length'
    length : int

# Serial specific
@dataclass
class SerialPortInstanciate(APICall):
    action = 'serial_adapter_inst'
    port : str
    baudrate : int
    timeout : TimeoutAPI
    stop_condition : StopConditionAPI
    rts_cts : bool

# Adapters common
@dataclass
class AdapterOpen(APICall):
    action = 'adapter_open'

@dataclass
class AdapterClose(APICall):
    action = 'adapter_close'

@dataclass
class AdapterWrite(APICall):
    action = 'adapter_write'
    data : bytes

@dataclass
class AdapterFlushRead(APICall):
    action = 'adapter_flush_read'

@dataclass
class AdapterRead(APICall):
    action = 'adapter_read'

@dataclass
class AdapterReadReturn(APICall):
    action = 'adapter_read_return'
    data : bytes
    return_metrics : dict = None

@dataclass
class ReturnStatus(APICall):
    action = 'return_status'
    success : bool
    error_message : str = ''

# Register apis
current_module = sys.modules[__name__]
API_CALLS_PER_ACTION = {getattr(obj, ACTION_ATTRIBUTE) : obj for obj in current_module.__dict__.values() if hasattr(obj, ACTION_ATTRIBUTE)}
register_api(API_CALLS_PER_ACTION)