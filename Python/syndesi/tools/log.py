# log.py
# Sébastien Deriaz
# 07.04.2024
# Log utilities
#
# Set log level, destination, etc...
from enum import Enum
import logging
from typing import List, Union

class LoggerAlias(Enum):
    ADAPTER = 'syndesi.adapter'
    PROTOCOL = 'syndesi.protocol'
    PROXY_SERVER = 'syndesi.proxy_server'
    CLI = 'syndesi.cli'

default_formatter = logging.Formatter('%(asctime)s:%(name)s:%(levelname)s:%(message)s')

def set_log_file(file : str, level : Union[str, int], loggers : Union[List[LoggerAlias], str] = 'all'):
    """
    Set log file

    Parameters
    ----------
    file : str
        File path, if None, file logging is disabled
    level : str or logging level
        info     : 'INFO'     or logging.INFO
        critical : 'CRITICAL' or logging.CRITICAL
        error    : 'ERROR'    or logging.ERROR
        warning  : 'WARNING'  or logging.WARNING
        info     : 'INFO'     or logging.INFO
        debug    : 'DEBUG'    or logging.DEBUG
    loggers : list of LoggerAlias or 'all'
        Which loggers to save to the file, 'all' by default
    """
    global file_handler

    if isinstance(loggers, str) and loggers == 'all':
        _all = True
    elif not isinstance(loggers, list):
        raise ValueError("Invalid argument loggers")

    # 1) Remove all file handlers from all loggers
    for alias in LoggerAlias:
        logger = logging.getLogger(alias.value)
        for h in logger.handlers:
            if isinstance(h, logging.FileHandler):
                logger.removeHandler(h)
        
    if file is not None:
        # 2) Create the new file handler
        file_handler = logging.FileHandler(file)
        file_handler.setFormatter(default_formatter)
        # 3) Add to the designated loggers
        for l in LoggerAlias:
            if loggers == 'all' or l.value in loggers:
                logger = logging.getLogger(l.value)
                logger.addHandler(file_handler)
                logger.setLevel(level)
    else:
        file_handler = None
    
def set_log_level(level : Union[str, int], loggers : Union[List[LoggerAlias], str] = 'all'):
    """
    Set log level, everything below or equal to the given level will be outputed to stdout/stderr.

    Parameters
    ----------
    level : str or logging level
        info     : 'INFO'     or logging.INFO
        critical : 'CRITICAL' or logging.CRITICAL
        error    : 'ERROR'    or logging.ERROR
        warning  : 'WARNING'  or logging.WARNING
        info     : 'INFO'     or logging.INFO
        debug    : 'DEBUG'    or logging.DEBUG
        None will disable logging
    loggers : list of LoggerAlias or 'all'
        Which loggers to save to the file, 'all' by default
    """
    global stream_handler

    if isinstance(loggers, str) and loggers == 'all':
        _all = True
    elif not isinstance(loggers, list):
        raise ValueError("Invalid argument loggers")


    # 1) Remove all stream handlers from all loggers
    for alias in LoggerAlias:
        logger = logging.getLogger(alias.value)
        for h in logger.handlers:
            if isinstance(h, logging.StreamHandler):
                logger.removeHandler(h)
        
    if level is not None:
        # 2) Create the new stream handler
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(default_formatter)
        # 3) Add to the designated loggers
        for l in LoggerAlias:
            if _all or l in loggers:
                logger = logging.getLogger(l.value)
                logger.addHandler(stream_handler)
                logger.setLevel(level)
    else:
        stream_handler = None