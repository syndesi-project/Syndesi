# backend_status.py
# 13.07.2025
# Sébastien Deriaz
"""
Backend status
"""

import argparse
import logging
import threading
import time
from multiprocessing.connection import Client, Pipe, wait
from time import sleep
from typing import cast

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from syndesi.adapters.backend.backend_tools import NamedConnection
from syndesi.tools.backend_logger import LogHandler
from syndesi.tools.log_settings import LoggerAlias

from ..tools.backend_api import (
    BACKEND_PORT,
    LOCALHOST,
    Action,
    backend_request,
)
from ..tools.log import log_manager

LOGGING_COLORS = {
    logging.DEBUG: "grey66",
    logging.INFO: "green",
    logging.WARNING: "yellow",
    logging.ERROR: "red",
    logging.CRITICAL: "bold purple",
}

logging.getLogger().setLevel(logging.CRITICAL + 1)


#pylint: disable=too-few-public-methods, too-many-instance-attributes
class BackendStatus:
    """
    Backend status, display live backend information like PID, connected clients, logs, etc...
    """
    DEFAULT_REFRESH_RATE = 0.5
    DEFAULT_N_CONSOLE_LINES = 20  # Number of lines in the console view
    CONNECTIONS_MIN_HEIGHT = 2

    # Display elements
    _pid : str
    _backend_status : str
    _main_table : Table
    _adapter_table : Table


    def __init__(self, input_args: list[str]) -> None:
        self.argument_parser = argparse.ArgumentParser()
        self.argument_parser.add_argument(
            "-l",
            "--live",
            type=float,
            default=False,
            help="Live mode, update status continuously at set refresh rate",
        )
        self.argument_parser.add_argument(
            "--log-lines",
            type=int,
            default=self.DEFAULT_N_CONSOLE_LINES,
            help="Number of log lines to display",
        )
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
            "--log-level", type=str, choices=list(logging._nameToLevel.keys())
        )  # pyright: ignore[reportPrivateUsage]

        args = self.argument_parser.parse_args(input_args)

        self._n_console_lines = args.log_lines
        self.host: str = args.address
        self.port: int = args.port
        self.live_delay: float | None = args.live

        # Buffer for last N_CONSOLE_LINES log messages
        self.console_lines: list[str] = []
        self.console_lock = threading.Lock()  # Lock for thread safety
        log_manager.enable_backend_logging()
        self._start_time = time.time()
        self.conn: NamedConnection | None = None

        self._log_handler = LogHandler()

        self._new_console_line_r, self._new_console_line_w = Pipe()

        self._init_display_elements()


    def _init_main_table(self):
        self._main_table = Table(box=None, padding=(0, 1))
        self._main_table.add_column(justify="right")
        self._main_table.add_column(justify="left")

    def _init_display_elements(self):
        self._init_main_table()
        self._pid = ""
        self._backend_status = "[red3]● Offline"
        self._monitoring_connections = Table(
            "",
            box=None,
            caption_justify="right",
            show_header=False,
            pad_edge=False,
        )
        self._adapter_table = Table("", box=None, caption_justify="right")

    def _make_new_connection(self):
        try:
            self.conn = NamedConnection(Client((self.host, self.port)))
        except (ConnectionRefusedError, OSError):
            self.conn = None
            sleep(0.1)
        else:
            backend_request(self.conn.conn, Action.SET_ROLE_MONITORING)

    #pylint: disable=too-many-locals, too-many-branches
    def _update_display_elements(self) -> bool:
        self._backend_status = "[green3]● Online"

        ready = wait([self.conn.conn, self._new_console_line_r])

        if self._new_console_line_r in ready:
            self._new_console_line_r.recv()
        elif self.conn.conn in ready:
            try:
                event = self.conn.conn.recv()
            except (ConnectionResetError, OSError, EOFError):
                self.conn = None
                return False

            action: Action = Action(event[0])
            if action == Action.ENUMERATE_ADAPTER_CONNECTIONS:
                adapter_table = Table(
                    "", box=None, caption_justify="right"
                )
                snapshot: dict[str, tuple[bool, list[str]]] = event[
                    1
                ]
                unique_clients: set[str] = set()
                for _, (_, adapter_clients) in snapshot.items():
                    unique_clients |= set(adapter_clients)
                for client in unique_clients:
                    adapter_table.add_column(
                        f"{client}", justify="center"
                    )

                for adapter, (
                    status,
                    adapter_clients,
                ) in snapshot.items():
                    status_indicator = (
                        "[green3]●" if status else "[red3]●"
                    )
                    client_indicators: list[str] = []
                    for client in unique_clients:
                        client_indicators.append(
                            "[green3]●[/]"
                            if client in adapter_clients
                            else "[red3]●[/]"
                        )
                    adapter_table.add_row(
                        f"{adapter} {status_indicator}",
                        *client_indicators,
                    )
            elif action == Action.ENUMERATE_MONITORING_CONNECTIONS:
                monitoring_connections = Table(
                    "",
                    box=None,
                    caption_justify="right",
                    show_header=False,
                    pad_edge=False,
                )
                # Update monitoring connections
                monitoring_response: list[tuple[str, str]] = event[
                    1
                ]

                for connection, desc in monitoring_response:
                    if (
                        connection
                        == log_manager.backend_logger_conn_description()
                        or connection == self.conn.local()
                    ):
                        style = ("grey50", "grey23")
                    else:
                        style = ("grey", "grey50")

                    monitoring_connections.add_row(
                        f"[{style[0]}]{connection}[/] [{style[1]}]({desc})[/]"
                    )
                for _ in range(
                    self.CONNECTIONS_MIN_HEIGHT
                    - len(monitoring_response)
                ):
                    monitoring_connections.add_row("")

            elif action == Action.BACKEND_STATS:
                # Update Backend stats
                pid_response: int = cast(int, event[1])
                self._pid = str(pid_response)

        return True

    def run(self) -> None:
        """
        Main backend status loop
        """
        self._log_handler.callback = self._add_line_status_screen
        logging.getLogger().addHandler(self._log_handler)

        self._init_display_elements()

        try:
            with Live(refresh_per_second=30) as live_display:
                while True:
                    if self.conn is None:
                        self._init_display_elements()
                        self._make_new_connection()

                    if self.conn is not None:
                        self._update_display_elements()

                    self._init_main_table()
                    self._main_table.add_column(justify="right")
                    self._main_table.add_column(justify="left")
                    self._main_table.add_row("Status :", self._backend_status)
                    self._main_table.add_row("PID :", self._pid)
                    self._main_table.add_row("Logger connections :", self._monitoring_connections)
                    self._main_table.add_row(
                        "Adapter connections :",
                        (self._adapter_table if self._adapter_table is not None else Text("")),
                    )

                    # Build the console panel
                    with self.console_lock:
                        console_content = "\n".join(self.console_lines) or " "
                    console_panel = Panel(
                        console_content,
                        title="Console",
                        height=self._n_console_lines + 2,  # +2 for panel borders
                        border_style="dim",
                        padding=(0, 1),
                    )

                    # Group the main table and console panel vertically
                    group = Group(self._main_table, console_panel)
                    live_display.update(group)

                    if self.live_delay is not None:
                        sleep(self.live_delay)
                    else:
                        break
        except KeyboardInterrupt:
            pass

    def _format_record(self, record: logging.LogRecord) -> str:
        color = LOGGING_COLORS.get(record.levelno)
        relative_time = record.created - self._start_time

        line = f"[{color}]{relative_time:7.3f} {record.levelname:<8} {record.msg}[/]"
        if record.name == LoggerAlias.BACKEND.value:
            line = f"[bold]{line}[/bold]"
        return line

    def _add_line_status_screen(self, record: logging.LogRecord) -> None:
        """
        Add a log message to the console buffer, with color formatting by log level.
        Thread-safe.
        """
        formated_text = self._format_record(record)
        with self.console_lock:
            self.console_lines.append(formated_text)
            if len(self.console_lines) > self._n_console_lines:
                self.console_lines = self.console_lines[-self._n_console_lines :]
        self._new_console_line_w.send(b"\x00")
