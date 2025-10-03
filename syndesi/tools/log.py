# File : logmanager.py
# Author : Sébastien Deriaz
# License : GPL

import logging
import threading
from typing import TextIO

from .backend_logger import BackendLogger
from .log_settings import LoggerAlias

class LogManager:
    _lock = threading.Lock()

    DEFAULT_FORMATTER = logging.Formatter(
        "%(asctime)s:%(name)s:%(levelname)s:%(message)s"
    )
    DEFAULT_LOG_LEVEL = logging.ERROR

    def __init__(self) -> None:
        self._file_handler: logging.Handler | None = None
        self._all_loggers = False
        self._loggers: list[str] = []
        self._level = self.DEFAULT_LOG_LEVEL
        self._stream_handler: logging.StreamHandler[TextIO] | None = None
        self._backend_logger: BackendLogger | None = None

    def enable_backend_logging(self) -> None:
        self._backend_logger = BackendLogger()
        self._backend_logger.start()

    def set_log_level(self, level: str | int) -> None:
        if isinstance(level, str):
            if not hasattr(logging, level.upper()):
                raise ValueError(f"Invalid log level: {level}")
            internal_level = getattr(logging, level.upper())
        elif isinstance(level, int):
            internal_level = level
        else:
            raise ValueError(f"Invalid level : {level}")

        self._level = internal_level
        self.update_loggers()

    def set_console_log(self, enabled: bool) -> None:
        if enabled:
            self._stream_handler = logging.StreamHandler()
            self._stream_handler.setFormatter(self.DEFAULT_FORMATTER)
        else:
            self._stream_handler = None

    def set_log_file(self, file: str | None) -> None:
        if file is not None:
            self._file_handler = logging.FileHandler(file)
            self._file_handler.setFormatter(self.DEFAULT_FORMATTER)
        else:
            if self._file_handler is not None:
                self._file_handler.close()
            self._file_handler = None

    def set_logger_filter(self, loggers: list[str] | str) -> None:
        self._all_loggers = False
        self._loggers = []
        if isinstance(loggers, list):
            self._loggers = loggers
        elif isinstance(loggers, str):
            if loggers == "all":
                self._all_loggers = True
            else:
                self._loggers = [loggers]
        else:
            raise ValueError("Invalid argument loggers")

    def update_loggers(self) -> None:
        # 1) Remove everything
        for alias in LoggerAlias:
            logger = logging.getLogger(alias.value)
            logger.handlers.clear()
        # 2) Update
        for alias in LoggerAlias:
            if self._all_loggers or alias.value in self._loggers:
                logger = logging.getLogger(alias.value)
                if self._file_handler is not None:
                    logger.addHandler(self._file_handler)
                if self._stream_handler is not None:
                    logger.addHandler(self._stream_handler)
                logger.setLevel(self._level)

    def backend_logger_conn_description(self) -> str:
        if self._backend_logger is None:
            return ""
        else:
            return self._backend_logger.conn_description


log_manager = LogManager()


def log(
    level: str | int | None = None,
    console: bool | None = None,
    file: str | None = None,
    loggers: list[str] | str | None = None,
) -> None:
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
    update = False
    if level is not None:
        log_manager.set_log_level(level)
        update = True
    if console is not None:
        log_manager.set_console_log(console)
        update = True
    if file is not None:
        log_manager.set_log_file(file)
        update = True
    if loggers is not None:
        log_manager.set_logger_filter(loggers)
        update = True

    if update:
        log_manager.update_loggers()
