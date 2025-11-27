# File : log_settings.py
# Author : Sébastien Deriaz
# License : GPL
"""
Log utilities
Set log level, destination, etc...
"""
import logging
from enum import Enum


class LoggerAlias(Enum):
    """
    Name of the Syndesi loggers inside the logging module
    """

    ADAPTER = "syndesi.adapter"
    PROTOCOL = "syndesi.protocol"
    CLI = "syndesi.cli"
    BACKEND = "syndesi.backend"
    ADAPTER_BACKEND = "syndesi.adapter_backend"
    BACKEND_LOGGER = "syndesi.backend_logger"


LOGGING_COLORS = {
    logging.DEBUG: "grey66",
    logging.INFO: "green",
    logging.WARNING: "yellow",
    logging.ERROR: "red",
    logging.CRITICAL: "bold purple",
}
