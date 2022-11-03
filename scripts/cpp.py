"""
C++ code generation class
"""

from commands import Command
from os.path import join, dirname
from utilities import replace_str
from settings import types
from typing import List

with open(join(dirname(__file__), "payload_class_template.cpp.txt")) as f:
    CPP_PAYLOAD_TEMPLATE = f.read()

TAB = 4*' '

class CPP():
    def __init__(self, commands_list  : List[Command]):
        """
        Instanciate a CPP code generation class with a list of Command objects
        """
        self._commands = commands_list

    def commands_enum(self):
        """
        Return an enum of commands
        """

        output = ''
        for i, command in enumerate(self._commands):
            if i > 0:
                output += ',\n'
            output += f"{TAB}{command.alias} = 0x{command.ID:04x}"
        
        return output

    def payloads(self):
        """
        Generate the class description for each payload
        """ 

        cpp_type_conversion = {
            types.double : lambda field : f"double {field.name};\n",
            types.uint : lambda field : f"uint{field.size*8}_t {field.name};\n",
            types.int  : lambda field : f"int{field.size*8}_t {field.name};\n",
            types.float : lambda field : f"float {field.name};\n",
            types.enum : lambda field : f"enum {field.name}_t {field.enum}{field.name};\n",
            types.char : lambda field : f"char {field.name}[{field.size}];\n",
            types.byte : lambda field : f"byte {field.name}[{field.size}];\n"
        }

        output = ''

        for command in self._commands:
            for fields, is_request in filter(lambda x : x[0] is not None, [(command.request_fields, True), (command.reply_fields, False)]):
                parse = ''
                build = ''
                variables = ''
                argument_constructor = ''
                arguments = ''
                length = ''

                for i, field in enumerate(fields):
                    if i > 0:
                        arguments += ', '
                        argument_constructor += ', '
                        length += ' + '


                    if field.type in [types.double, types.int, types.uint, types.float, types.enum]:
                        # Copy with endian conversion
                        parse += 2*TAB + f"pos += ntoh(payloadBuffer->data() + pos, reinterpret_cast<char*>(&{field.name}), {field.size});\n"
                        build += 2*TAB + f"pos += hton(reinterpret_cast<char*>(&{field.name}), payloadBuffer->data() + pos, {field.size});\n"
                        variables += TAB + cpp_type_conversion[field.type](field)
                        arguments += cpp_type_conversion[field.type](field).replace(';', '')
                        
                    elif field.type in [types.char, types.byte]:
                        # Array
                        if field.fixed_size:
                            variables += TAB + cpp_type_conversion[field.type](field)
                            parse += 2*TAB + f"{field.name} = payloadBuffer->data() + pos;"
                        else:
                            variables += TAB + f'Buffer {field.name};\n'
                            parse += 2*TAB + f"{field.name}.fromParent(payloadBuffer, pos, {field.size});"
                        parse += 2*TAB + f"pos += {field.size};"                            
                    else:
                        raise ValueError(f"Unsupported type : {field.type}")
                    
                    length += str(field.size)
                
                if not length:
                    length = '0'
                length += ';'

                output += replace_str(CPP_PAYLOAD_TEMPLATE, {
                    "alias" : f"{command.alias}_{'request' if is_request else 'reply'}",
                    "values" : variables,
                    "parse_function" : parse,
                    "length_function" : 2*TAB + 'return ' + length,
                    "build_function"  : build,
                    #"constructor" : TAB + f"{self.name}({arguments}) : {argument_constructor}{{}}"
                    "constructor" : '',
                    "command" : TAB+f"cmd_t getCommand() {{return 0x{command.ID:04X};}}",
                })
                #argument_constructor += f"{field.name}({field.name})"
        return output

    def defines(self, request):
        """
        Generate a list of defines for each command

        //#define USE_command1_callback 
        //#define USE_command2_callback 
        ...

        Parameters
        ----------
        request : bool
            Request mode / reply mode

        Returns
        -------
        output : str
        """

        output = ''

        i = 0
        for command in self._commands:
            if command.has_request and request:
                output += f'//#define USE_{command.alias.upper()}_REQUEST_CALLBACK\n'
            elif command.has_reply and (not request):
                output += f'//#define USE_{command.alias.upper()}_REPLY_CALLBACK\n'
        return output

    def switch(self, request):
        """
        Returns a switch statement to test each command case

        Request mode is for the processing of requests commands

        Parameters
        ----------
        request : bool
            

        Returns
        -------
        output : str
        """
        TAB = 4
        output = ''

        for command in self._commands:            
            if request and command.has_request:
                output += f'#if defined(USE_{command.alias.upper()}_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)\n'                
                output += ' '*2*TAB + f'case commands::{command.alias}:\n'
                #output += ' '*3*TAB + f'if({command}_{command_type} != NULL) {{\n'
                output += ' '*3*TAB + f'request = new {command.alias}_request(requestPayloadBuffer);\n'
                output += ' '*3*TAB + f'reply = new {command.alias}_reply();\n'
                output += ' '*3*TAB + f'_callbacks->{command.alias}_request_callback(*(static_cast<{command.alias}_request*>(request)), static_cast<{command.alias}_reply*>(reply));\n'
                #output += ' '*3*TAB + '}\n'
                output += ' '*3*TAB + f'break;\n'
                output += '#endif\n'
            elif not request and command.has_reply:
                output += f'#if defined(USE_{command.alias.upper()}_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)\n'
                output += ' '*2*TAB + f'case commands::{command.alias}:\n'
                #output += ' '*3*TAB + f'if({command}_{command_type} != NULL) {{\n'
                output += ' '*3*TAB + f'reply = new {command.alias}_reply(replyPayloadBuffer);\n'
                output += ' '*3*TAB + f'_callbacks->{command.alias}_reply_callback(*(static_cast<{command.alias}_reply*>(reply)));\n'
                #output += ' '*3*TAB + '}\n'
                output += ' '*3*TAB + f'break;\n'
                output += '#endif\n'
        return output

    def callbacks(self):
        """
        Inits callbacks defines at NULL

        #define DEVICE_DISCOVER_REQUEST_CALLBACK NULL
        ...

        Returns
        -------
        defines : str
        """

        TAB = 4
        output = ''
        for command in self._commands:
            if command.has_request:
                output += f'#if defined(USE_{command.alias}_REQUEST_CALLBACK) && defined(SYNDESI_DEVICE_MODE)\n'
                output += TAB*' ' + f'void {command.alias}_request_callback({command.alias}_request& request, {command.alias}_reply* reply);\n'
                output += f'#endif\n'
            if command.has_reply:
                output += f'#if defined(USE_{command.alias}_REPLY_CALLBACK) && defined(SYNDESI_HOST_MODE)\n'
                output += TAB*' ' + f'void {command.alias}_reply_callback({command.alias}_reply& reply);\n'
                output += f'#endif\n'
        return output

    def commands_names_switch(self):
        """
        Return a C++ map of command name in regard to the command ID
        {ID 0, name 0},
        {ID 1, name 1},
        etc...

        Returns
        -------
        names : str
        """
        names = ""

        for i, command in enumerate(self._commands):
            names += 2*TAB + f"case 0x{command.ID:04X}:\n"
            names += 3*TAB + f"return \"{command.alias}\";\n"
            names += 3*TAB + "break;\n"

        return names

    def commands_ids(self):
        """
        Return a list of commands IDs as such :

        0x0001,
        0x0101,
        ...
        
        Returns
        -------
        output : str
        """
        output = ""
        for i, command in enumerate(self._commands):
            if i > 0:
                output += ',\n'
            output += f"0x{command.ID:04X}"
        return output


            





