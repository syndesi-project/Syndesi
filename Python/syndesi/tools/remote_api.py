# remote.py
# Sébastien Deriaz
# 29.05.2024
from ..adapters import IP
import json
from dataclasses import dataclass, fields, Field
from typing import Tuple, Union, Dict
from enum import Enum
import sys
import quopri

class RemoteException(Exception):
    pass

class APICall:
    action = ''
    _keyword = ''

    def __init__(self, *args, **kwargs) -> None:
        #if getattr(self, )
        print(f"args : {args}")
        print(f"kwargs : {kwargs}")
        

    def encode(self) -> bytes:
        cls_fields: Tuple[Field, ...] = fields(self)
        data = {}
        
        # Add action field
        data[ACTION_ATTRIBUTE] = self.action
        # Add other fields
        for field in cls_fields:
            field_data = getattr(self, field.name)
            if isinstance(field_data, Enum):
                entry = field_data.value
            elif isinstance(field_data, bytes):
                entry = quopri.encodestring(field_data).decode('ASCII')
            elif isinstance(field_data, str):
                entry = quopri.encodestring(field_data.encode('utf-8')).decode('ASCII')
            else:
                entry = field_data

            data[field.name] = entry
        return json.dumps(data)

    # def parse(self, data : dict):
    #     cls_fields: Tuple[Field, ...] = fields(self)
        
    #     for field in cls_fields:
    #         setattr(self, field.name, data[field.name])
            
    #         field_data = getattr(self, field.name)
    #         if isinstance(field_data, Enum):
    #             entry = field_data.value

    #         data[field.name] = entry

    #     return data
@dataclass
class IPAdapterInstanciate(APICall):
    action = 'adapter_inst'
    address : str
    port : int
    transport : IP.Protocol
    buffer_size : int = IP.DEFAULT_BUFFER_SIZE

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

current_module = sys.modules[__name__]
ACTION_ATTRIBUTE = 'action'

API_CALLS_PER_ACTION : Dict[str, APICall]
API_CALLS_PER_ACTION = {getattr(obj, ACTION_ATTRIBUTE) : obj for obj in current_module.__dict__.values() if hasattr(obj, ACTION_ATTRIBUTE)}

def parse(data : Union[str, bytes]) -> APICall:
    print(f"Parsing {data}")
    json_data = json.loads(data)
    action = json_data[ACTION_ATTRIBUTE]
    json_data.pop(ACTION_ATTRIBUTE)
    arguments = json_data
    # Find the right API call and return it
    return API_CALLS_PER_ACTION[action](**arguments)