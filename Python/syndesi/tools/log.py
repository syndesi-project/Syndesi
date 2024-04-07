# log.py
# Sébastien Deriaz
# 07.04.2024
# Log utilities
#
# Set log level, destination, etc...
from enum import Enum
import logging
from typing import List, Union
import os

class LoggerAlias(Enum):
    ADAPTER = 'adapter'
    PROTOCOL = 'protocol'

file_handlers = []
stream_handlers = []

loggers_handlers = {l : [] for l in LoggerAlias}

def set_log_file(file : str, loggers : Union[List[LoggerAlias], str] = 'all'):
    """
    Set log file

    Parameters
    ----------
    file : str
        File path, if None, file logging is disabled
    loggers : list of LoggerAlias or 'all'
        Which loggers to save to the file, 'all' by default
    """
    if file is None:
        # Remove the handler from the loggers
        handler = None

    filepath = os.path.normpath(file)
    # Check if the handler exists
    h : logging.FileHandler
    for h in file_handlers:
        if h.baseFilename == filepath:
            handler = h
            break
    else:
        # Create a new handler
        handler = logging.FileHandler(filepath)

    



    loggers = Loggers(loggers)
    loggers_list = []
    if loggers == Loggers.ALL:
        # Loop over all loggers
        for l in Loggers:
            if l != Loggers.ALL:
                loggers_list.append(l)
    else:
        loggers_list.append(loggers)
        
    logging.getLogger('test').hasHandlers()



def set_log_mode():
    """
    Set stdout/stderr log mode


    
    """

    pass

