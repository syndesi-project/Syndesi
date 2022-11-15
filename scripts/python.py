"""
Python code generation class
"""

from commands import Command
from os.path import join, dirname
from utilities import replace_str
from settings import types
from typing import List



TAB = 4*' '

class Python():
    def __init__(self, commands_list  : List[Command]):
        """
        Instanciate a Python code generation class with a list of Command objects
        """
        self._commands = commands_list

    def payloads(self, payload_template):
        """
        Outputs a list of payloads

        Parameters
        ----------
        payload_template : str
            Path to the payload teamplate file

        Returns
        -------
        payloads : str
        
        """

        with open(payload_template) as f:
            PY_PAYLOAD_TEMPLATE = f.read()

        py_type_conversion = {
            types.double : lambda field : f"{field.name} : float\n",
            types.uint : lambda field : f"{field.name} : int\n",
            types.int  : lambda field : f"{field.name} : int\n",
            types.float : lambda field : f"{field.name} : float\n",
            types.enum : lambda field : f"class {field.name}(Enum):\n{2*TAB}{(chr(10) + 2*TAB).join([f'{d[1]} = {d[0]}' for d in field.enum])}\n",
            types.char : lambda field : f"{field.name} : bytearray\n",
            types.byte : lambda field : f"{field.name} : bytearray\n"
        }

        payloads = ''

        for command in self._commands:
            for fields, is_request in filter(lambda x : x[0] is not None, [(command.request_fields, True), (command.reply_fields, False)]):
                
                variables = ''
                arguments = ''
                length = ''
                parameters = ''
                lib_functions = ''
                setattr_str = f'{2*TAB}if False:\n{3*TAB}pass\n'
                getattr_str = f'{2*TAB}if False:\n{3*TAB}pass\n'


                for i, field in enumerate(fields):
                    if i > 0:
                        arguments += ', '
                        length += ' + '
                        parameters += '\n'


                    if field.type in py_type_conversion.keys():
                        # Copy with endian conversion
                        variables += TAB + py_type_conversion[field.type](field)
                        arguments += py_type_conversion[field.type](field).replace(';', '')
                        parameters += f"{3*TAB} - {field.name} : {field.type.name}"

                        # Set the C-Interface parameters



                        lib_functions += f'{2*TAB}self._lib.set{command.alias}_{field.name}.restype = None\n'
                    else:
                        raise ValueError(f"Unsupported type : {field.type}")
                

                payloads += replace_str(PY_PAYLOAD_TEMPLATE, {
                    "alias" : f"{command.alias}_{'request' if is_request else 'reply'}",
                    "values" : variables,
                    "parameters" : f'{3*TAB}None' if parameters == '' else parameters ,
                    "id" : f"0x{command.ID:04X}",
                    "request_nReply" : str(is_request)
                })
        return payloads







