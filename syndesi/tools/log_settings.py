# File : log.py
# Author : Sébastien Deriaz
# License : GPL
#
# Log utilities
# Set log level, destination, etc...

from enum import Enum


class LoggerAlias(Enum):
    ADAPTER = "syndesi.adapter"
    PROTOCOL = "syndesi.protocol"
    CLI = "syndesi.cli"
    BACKEND = "syndesi.backend"
    ADAPTER_BACKEND = "syndesi.adapter_backend"
    BACKEND_LOGGER = "syndesi.backend_logger"
