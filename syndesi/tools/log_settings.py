# File : log_settings.py
# Author : Sébastien Deriaz
# License : GPL
"""
Log utilities
Set log level, destination, etc...
"""
import logging
from enum import StrEnum


class LoggerAlias(StrEnum):
    """
    Name of the Syndesi loggers inside the logging module
    """

    ADAPTER = "syndesi.adapter"
    PROTOCOL = "syndesi.protocol"
    CLI = "syndesi.cli"
    ADAPTER_WORKER = "syndesi.adapterworker"
    FRAMER = "syndesi.framer"
    ENGINE = "syndesi.engine"
    REACTOR = "syndesi.reactor"


LOGGING_COLORS = {
    logging.DEBUG: "grey66",
    logging.INFO: "green",
    logging.WARNING: "yellow",
    logging.ERROR: "red",
    logging.CRITICAL: "bold purple",
}
