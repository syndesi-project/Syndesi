# logger.py
# Sébastien Deriaz
# 11.03.2024
#
# A class to manage adapter logging
from enum import Enum
from typing import Union
from dataclasses import dataclass

class Entry(dataclass):
    read_nWrite : bool
    timestamp : float
    data : bytes
    description : str = None

class LoggerClientType:
    ADAPTER = 'adapter'
    PROTOCOL = 'protocol'
    DRIVER = 'driver'

class LoggerIdentifier:
    def __init__(self, client_type : Union[LoggerClientType, str], keywords : dict) -> None:
        """
        This class holds the client's information recorded for logging

        parameters
        ----------
        client_type : LoggerClientType or str
        keywords : dict
        """
        if isinstance(client_type, str):
            self._type = LoggerClientType(client_type)
        elif isinstance(client_type):
            self._type = client_type
        else:
            raise ValueError('Invalid client_type type')

        self._keywords = keywords

class Logger:
    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls._values = {}
            cls.instance = super(Logger, cls).__new__(cls)
            return cls.instance

    def log(self, identifier : LoggerIdentifier, entry : Entry):
        self._values[identifier].append(entry)