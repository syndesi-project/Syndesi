# shell.py
# Sébastien Deriaz
# 30.04.2024
from enum import Enum

class Arguments(Enum):
    PORT = 'port' # Serial port or ip port
    IP = 'ip'
    BAUDRATE = 'baudrate'
    UDP = 'udp'
    ENABLE_RTS_CTS = 'rts-cts'

