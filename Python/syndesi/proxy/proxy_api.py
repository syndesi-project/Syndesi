# proxy_api.py
# Sébastien Deriaz
# 29.05.2024

import sys
from dataclasses import dataclass
from ..adapters.stop_conditions import Length, Termination, StopCondition
from ..adapters.timeout import Timeout

from ..api.api import APICall, ACTION_ATTRIBUTE, register_api, APIItem

class ProxyException(Exception):
    pass

@dataclass
class TimeoutAPI(APIItem):
    name = 'timeout'
    response : float
    continuation : float
    total : float
    on_response : str
    on_continuation : str
    on_total : str

def timeout_to_api(timeout : Timeout) -> TimeoutAPI:
    if timeout is None:
        return None
    else:
        return TimeoutAPI(
            response=timeout._response,
            continuation=timeout._continuation,
            total=timeout._total,
            on_response=timeout._on_response,
            on_continuation=timeout._on_continuation,
            on_total=timeout._on_total
        )

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

def stop_condition_to_api(stop_condition : StopCondition):
    if stop_condition is None:
        return None
    elif isinstance(stop_condition, Length):
        return LengthAPI(length=stop_condition._N)
    elif isinstance(stop_condition, Termination):
        return TerminationAPI(sequence=stop_condition._termination)
# IP specific
@dataclass
class IPInstanciate(APICall):
    action = 'ip_adapter_inst'
    address : str
    port : int
    transport : str
    buffer_size : int
    timeout : TimeoutAPI

# Serial specific
@dataclass
class SerialPortInstanciate(APICall):
    action = 'serial_adapter_inst'
    port : str
    baudrate : int
    timeout : TimeoutAPI
    stop_condition : StopConditionAPI
    rts_cts : bool

# VISA specific
@dataclass
class VisaInstanciate(APICall):
    action = 'visa_instanciate'
    resource : str
    

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