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


def log_settings(level : Union[str, int], console : bool = True, file : str = None, loggers : Union[List[LoggerAlias], str] = 'all'):
    """
    Configure syndesi logging
    
    Parameters
    ----------
        level : str or logging level
            . 'INFO'    
            . 'CRITICAL'
            . 'ERROR'   
            . 'WARNING' 
            . 'INFO'    
            . 'DEBUG'
        console : bool
            Print logging information to the console (True by default). Optional
        file : str
            File path, if None, file logging is disabled. Optionnal
        loggers : list
            Select which logger modules are updated (see LoggerAlias class). Optional
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
        # 2) Create the new file and stream handlers
        file_handler = logging.FileHandler(file)
        file_handler.setFormatter(default_formatter)
    else:
        file_handler = None
    
    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(default_formatter)
    else:
        stream_handler = None
    # 3) Add to the designated loggers
    for l in LoggerAlias:
        if loggers == 'all' or l.value in loggers:
            logger = logging.getLogger(l.value)
            if file_handler is not None:
                logger.addHandler(file_handler)
            if stream_handler is not None:
                logger.addHandler(stream_handler)
            logger.setLevel(level)
        