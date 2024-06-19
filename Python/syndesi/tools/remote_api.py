# remote.py
# Sébastien Deriaz
# 29.05.2024
from ..adapters import IP
import json
from dataclasses import dataclass, fields, Field
from typing import Tuple, Union
from enum import Enum

class RemoteException(Exception):
    pass

class APICall:
    action = ''
    _keyword = ''

    # def __init__(self, data_to_parse : dict = None) -> None:
    #     if data_to_parse is not None:
    #         self.parse(data_to_parse)
        

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
            else:
                entry = field_data

            data[field.name] = entry
        print(f"Data = {data}")
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

ACTION_ATTRIBUTE = 'action'
API_CALLS_PER_ACTION = {getattr(c, ACTION_ATTRIBUTE) : c for c in [AdapterOpen, IPAdapterInstanciate]}

def parse(data : Union[str, bytes]) -> APICall:
    print(f"Parsing {data}")
    json_data = json.loads(data)
    action = json_data[ACTION_ATTRIBUTE]
    json_data.pop(ACTION_ATTRIBUTE)
    arguments = json_data
    # Find the right API call and return it
    return API_CALLS_PER_ACTION[action](**arguments)

#     # class Keywords:
#     #     ACTION = 'action'
#     #     class Action:
#     #         ADAPTER_OPEN = 'open'
#     #         ADAPTER_INSTANCIATE = 'inst'

#     #     ADAPTER_OPTIONS = 'adapter_options'
#     #     ADAPTER_TYPE = 'type'
#     #     IP_ADAPTER_ADDRESS = 'address'
#     #     IP_ADAPTER_PORT = 'port'
#     #     IP_ADAPTER_TRANSPORT = 'transport'
#     #     IP_ADAPTER_BUFFER_SIZE = 'buffer_size'
#     #     TIMEOUT = 'timeout'
#     #     TIMEOUT_RESPONSE = 'resp'
#     #     TIMEOUT_ON_RESPONSE = 'on_resp'
#     #     TIMEOUT_CONTINUATION = 'cont'
#     #     TIMEOUT_ON_CONTINUATION = 'on_cont'
#     #     TIMEOUT_TOTAL = 'total'
#     #     TIMEOUT_ON_TOTAL = 'on_total'
#     #     STOP_CONDITION = 'stop-condition'
#     #     STOP_CONDITION_TYPE = 'type'
#     #     STOP_CONDITION_SEQUENCE = 'sequence'
#     #     STOP_CONDITION_LENGTH = 'length'
#     #     STATUS = 'status'
#     #     STATUS_OK = 'ok'
#     #     STATUS_ERROR = 'error'
#     #     STATUS_MESSAGE = 'message'

#     #     STOP_CONDITION_TYPE = {
#     #         Termination : 'termination',
#     #         Length : 'length'
#     #     }

#     #     ADAPTER_TYPE = {
#     #         IP : 'ip',
#     #         SerialPort : 'serial',
#     #         VISA : 'visa'
#     #     }

#     def parse(self, fragment : str):
#         # Parse JSON from fragment
#         pass


# class MasterAPI(API):

#     def instanciate_adapter(self, adapter : Adapter):
#         data = {}
#         data[self.Keywords.ACTION_KEYWORD] = self.Keywords.Action.ADAPTER_INSTANCIATE_KEYWORD
#         data[self.Keywords.ADAPTER_OPTIONS] = {
#             self.Keywords.ADAPTER_TYPE : self.Keywords.ADAPTER_TYPE[type(adapter)]
#         }
#         if isinstance(adapter, IP):
#             data[self.Keywords.ADAPTER_OPTIONS].update({
#                 self.Keywords.IP_ADAPTER_ADDRESS : adapter._address,
#                 self.Keywords.IP_ADAPTER_PORT : adapter._port,
#                 self.Keywords.IP_ADAPTER_TRANSPORT : adapter._transport.value,
#                 self.Keywords.IP_ADAPTER_BUFFER_SIZE : adapter._buffer_size
#             })
#         data.update({
#             self.Keywords.TIMEOUT : {
#                 self.Keywords.TIMEOUT_RESPONSE : adapter._timeout._response,
#                 self.Keywords.TIMEOUT_ON_RESPONSE : adapter._timeout._on_response.value,
#                 self.Keywords.TIMEOUT_CONTINUATION : adapter._timeout._continuation,
#                 self.Keywords.TIMEOUT_ON_CONTINUATION : adapter._timeout._on_continuation.value,
#                 self.Keywords.TIMEOUT_TOTAL : adapter._timeout._total,
#                 self.Keywords.TIMEOUT_ON_TOTAL : adapter._timeout._on_total.value
#             },
#         })

#         if adapter._stop_condition is not None:
#             data.update({self.Keywords.STOP_CONDITION : {
#                 self.Keywords.STOP_CONDITION_TYPE : self.Keywords.STOP_CONDITION_TYPE[type(adapter._stop_condition)],
#                 }
#             })
#             if isinstance(adapter._stop_condition, Termination):
#                 data[self.Keywords.STOP_CONDITION].update({
#                     self.Keywords.STOP_CONDITION_SEQUENCE : adapter._stop_condition._termination
#                 })
#             elif isinstance(adapter._stop_condition, Length):
#                 data[self.Keywords.STOP_CONDITION].update({
#                     self.Keywords.STOP_CONDITION_LENGTH : adapter._stop_condition._N
#                 })

#         return json.dumps(data)

#     def open_adapter(self):
#         data = {}
#         data[self.Keywords.ACTION] = self.Keywords.Action.ADAPTER_OPEN

#     def check(self, fragment : str) -> bool:
#         if fragment[self.Keywords.STATUS] != self.Keywords.STATUS_OK:
#             raise RemoteException(fragment[self.Keywords.STATUS_MESSAGE])

# class SlaveAPI(API):
#     def parse(self, fragment) -> API.Keywords.ACTION:
#         if self.Keywords.ACTION not in fragment:
#             # There is an error, return nothing
#             return None
        
#         return self.Keywords.Action(fragment[self.Keywords.ACTION])

#     def get_adapter_options(self, fragment):

