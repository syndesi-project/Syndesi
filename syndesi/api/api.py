import quopri
from typing import Tuple, Union, Dict
from enum import Enum
from dataclasses import dataclass, fields, Field
import json

APIS = {}

def register_api(apis : dict):
    """
    Register apis

    Parameters
    ----------
    apis : dict
        {'action' : APICall} class dictionary
    """
    APIS.update(apis)

ACTION_ATTRIBUTE = 'action'

class APIItem:
    pass

class APICall:
    action = ''
    _keyword = ''        

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

def parse(data : Union[str, bytes]) -> APICall:
    json_data = json.loads(data)
    action = json_data[ACTION_ATTRIBUTE]
    json_data.pop(ACTION_ATTRIBUTE)
    arguments = json_data
    # Find the right API call and return it
    if action not in APIS:
        raise RuntimeError(f"API action '{action}' not registered")

    converted_arguments = {}
    # Convert each argument according to the class field types
    api_fields: Tuple[Field, ...] = fields(APIS[action])
    
    for field in api_fields:
        if field.name not in arguments:
            raise RuntimeError(f"Field '{field.name}' missing from arguments")

        if field.type == bytes:
            # Convert back
            converted_arguments[field.name] = quopri.decodestring(arguments[field.name])
        elif field.type == str:
            converted_arguments[field.name] = quopri.decodestring(arguments[field.name]).decode('utf-8')
        elif field.type == Enum:
            converted_arguments[field.name] = field.type(arguments[field.name])
        else:
            converted_arguments[field.name] = arguments[field.name]

    return APIS[action](**converted_arguments)