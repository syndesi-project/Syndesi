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
    int = auto()
    uint = auto()
    float = auto()
    double = auto()
    char = auto()
    enum = auto()
    byte = auto()

ALLOWED_TYPES = {
    'int' : types.int,
    'uint' : types.uint,
    'float' : types.float,
    'double' : types.double,
    'char' : types.char,
    'byte' : types.byte,
    # Matches anything that looks like {A,B,C,D}
    '{([a-zA-Z _0-9]+)(,[a-zA-Z _0-9]+)+}' : types.enum
}