from enum import Enum, auto

# Number of bytes per command
COMMAND_BYTES = 2

# Yaml keys
YAML_COMMANDS_LIST_KEY = "Commands"
YAML_ALIAS_KEY = "alias"
YAML_ID_KEY = "ID"
YAML_COMMENT_KEY = "comment"
YAML_REQUEST_CONTENT_KEY = "request_content"
YAML_REPLY_CONTENT_KEY = "reply_content"
YAML_SETTINGS_KEY = "Settings"
YAML_SETTINGS_ENDIAN_KEY = "endian"
YAML_SIZE_KEY = "size"
YAML_TYPE_KEY = "type"



class types(Enum):
    short = auto()
    ushort = auto()
    int = auto()
    uint = auto()
    longlong = auto()
    ulonglong = auto()
    float = auto()
    double = auto()
    char = auto()
    enum = auto()
    byte = auto()

# Number of bytes for each type (with fixed size)
SIZE = {
    types.short : 2,
    types.ushort : 2,
    types.int : 4,
    types.uint : 4,
    types.longlong : 8,
    types.ulonglong : 8,
    types.float : 4,
    types.double : 8,
    types.enum : 1 
}

ALLOWED_TYPES = {
    'int' : types.int,
    'uint' : types.uint,
    'float' : types.float,
    'double' : types.double,
    'char' : types.char,
    'byte' : types.byte,
    '---' : types.enum # Enum is detected by being a list
}