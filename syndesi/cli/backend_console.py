# backend_status.py
# 13.07.2025
# Sébastien Deriaz

import argparse
import logging
import time
from collections.abc import Callable
from multiprocessing.connection import Connection
from time import sleep
from typing import Any

from rich.console import Console
from rich.text import Text

from ..tools.backend_api import BACKEND_PORT, LOCALHOST
from ..tools.backend_logger import BackendLogger
from ..tools.log_settings import LoggerAlias

LOGGING_COLORS = {
    logging.DEBUG: "grey66",
    logging.INFO: "green",
    logging.WARNING: "yellow",
    logging.ERROR: "red",
    logging.CRITICAL: "bold purple",
}

logging.getLogger().setLevel(logging.CRITICAL + 1)


class LogHandler(logging.Handler):
    def __init__(
        self, callback: Callable[[logging.LogRecord], None] | None = None
    ) -> None:
        super().__init__()
        self.callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        if self.callback is not None:
            self.callback(record)


class BackendConsole:
    def __init__(self, input_args: list[str]) -> None:
        self.argument_parser = argparse.ArgumentParser()
        self.argument_parser.add_argument(
            "-a",
            "--address",
            type=str,
            default=LOCALHOST,
            help="Listening address, set it to the interface that will be used by the client",
        )
        self.argument_parser.add_argument(
            "-p", "--port", type=int, default=BACKEND_PORT
        )
        self.argument_parser.add_argument(
            "-l", "--log-level", type=str, choices=list(logging._nameToLevel.keys())
        )  # pyright: ignore[reportPrivateUsage]

        args = self.argument_parser.parse_args(input_args)

        self.address = args.address
        self.port = args.port

        self._console = Console()

        self._log_handler = LogHandler()
        self._log_handler.callback = self._add_line

        logging.getLogger().addHandler(self._log_handler)
        self._start_time = time.time()
        self.conn: Connection[Any, Any] | None = None
        self._backend_logger = BackendLogger()

    def run(self) -> None:
        self._backend_logger.start()
        try:
            while True:
                sleep(1)
        except KeyboardInterrupt:
            pass

    def _format_record(self, record: logging.LogRecord) -> str:
        color = LOGGING_COLORS.get(record.levelno)
        relative_time = record.created - self._start_time

        line = f"[{color}]{relative_time:7.3f} {record.levelname:<8} {record.msg}[/]"
        if record.name == LoggerAlias.BACKEND.value:
            line = f"[bold]{line}[/bold]"
        elif record.name == LoggerAlias.BACKEND_LOGGER.value:
            line = f"[italic]{line}[/italic]"
        return line

    def _add_line(self, record: logging.LogRecord) -> None:
        formated_text = self._format_record(record)
        self._console.print(Text.from_markup(formated_text), markup=True)
