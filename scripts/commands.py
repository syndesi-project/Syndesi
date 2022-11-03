from settings import *
import re




class Command():
    def __init__(self, data):
        """
        Command instance
        """
        self.alias = data[YAML_ALIAS_KEY]
        self.has_request = YAML_REQUEST_CONTENT_KEY in data
        self.has_reply = YAML_REPLY_CONTENT_KEY in data
        self.ID = data[YAML_ID_KEY]

        if self.has_request:
            fields_description = data[YAML_REQUEST_CONTENT_KEY]
            if fields_description is None:
                self.request_fields = []
            else:
                self.request_fields = [Field(*f) for f in data[YAML_REQUEST_CONTENT_KEY].items()]
        else:
            self.request_fields = None

        if self.has_reply:
            fields_description = data[YAML_REPLY_CONTENT_KEY]
            if fields_description is None:
                self.reply_fields = []
            else:
                self.reply_fields = [Field(*f) for f in data[YAML_REPLY_CONTENT_KEY].items()]
        else:
            self.reply_fields = None




    def __repr__(self):
        return self.__str__()

    def __str__(self):
        output = f"""Command {self.alias}
{'request':>15} : {'yes' if self.has_request else 'no'}
{'reply':>15} : {'yes' if self.has_reply else 'no'}"""
        if self.has_request:
            output += f"""
{'request fields':>15} : {'empty' if self.request_fields is None else self.request_fields}"""
        if self.has_reply:
            output += f"""
{'reply fields':>15} : {'empty' if self.reply_fields is None else self.reply_fields}"""
        return output


class Field():
    def __init__(self, name, description):
        """
        Field instance
        """
        # Name
        self.name = name
        # Size (fixed or variable)
        self.size = description[YAML_SIZE_KEY]
        if self.size is int:
            self.fixed_size = True
        else:
            self.fixed_size = False
        # Type
        
        type_string = description[YAML_TYPE_KEY]
        for pattern_string, type_class in ALLOWED_TYPES.items():
            if re.match(pattern_string, type_string):
                self.type = type_class
                if self.type == types.enum:
                    self.enum = type_string
                else:
                    self.enum = None
                break
        else:
            raise ValueError(f"Field '{self.name}' has invalid type : {self.type}")
    
    def __repr__(self):
        return self.__str__()

    def __str__(self):
        return f"{self.name}({self.size}/{self.type.name})"

