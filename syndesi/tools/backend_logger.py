# File : backend_logger.py
# Author : Sébastien Deriaz
# License : GPL
#
# This class starts a thread to grab log records from the backend and emit them here
# in their respective loggers

import logging
import threading
from multiprocessing.connection import Client
from time import sleep
from typing import Callable

from syndesi.adapters.backend.backend_tools import NamedConnection
from syndesi.tools.errors import BackendCommunicationError
from syndesi.tools.log_settings import LoggerAlias

from .backend_api import BACKEND_PORT, Action, backend_request, default_host

class LogHandler(logging.Handler):
    """
    Log handler, receives log records and pushes them to a specified callback
    """
    def __init__(
        self, callback: Callable[[logging.LogRecord], None] | None = None
    ) -> None:
        super().__init__()
        self.callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        if self.callback is not None:
            self.callback(record)

class BackendLogger(threading.Thread):
    def __init__(self, *, callback: Callable[[logging.LogRecord], None] | None = None) -> None:
        self._conn_description_lock = threading.Lock()
        self.conn_description = ""
        self._logger = logging.getLogger(LoggerAlias.BACKEND_LOGGER.value)
        self._logger.setLevel(logging.DEBUG)
        self._callback = callback
        super().__init__(daemon=True)

    def run(self) -> None:
        conn = None
        loggers: dict[str, logging.Logger] = {}
        while True:
            if conn is None:
                try:
                    conn = NamedConnection(Client((default_host, BACKEND_PORT)))
                except ConnectionRefusedError:
                    conn = None
                    sleep(0.1)
                    continue
                else:
                    with self._conn_description_lock:
                        self.conn_description = conn.local()
                    self._logger.info("Backend connected")

                try:
                    backend_request(conn.conn, Action.SET_ROLE_LOGGER)
                except BackendCommunicationError:
                    conn.conn.close()
                    conn = None
                    sleep(0.1)
                    continue

            else:
                try:
                    record: logging.LogRecord = conn.conn.recv()
                except (EOFError, OSError, Exception):
                    self._logger.info("Backend disconnected")
                    sleep(0.1)
                    conn.conn.close()
                    conn = None
                else:
                    logger_name = record.name
                    if logger_name not in loggers:
                        loggers[logger_name] = logging.getLogger(logger_name)
                    loggers[logger_name].handle(record)
                    self._callback(record)
