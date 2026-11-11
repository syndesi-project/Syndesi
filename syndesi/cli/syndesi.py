# File : syndesi.py
# Author : Sébastien Deriaz
# License : GPL
"""
Main syndesi CLI script
"""

import argparse
import logging
from enum import Enum
from importlib.util import find_spec

from .terminal import Terminal

from .. import __version__


class SyndesiCommand(Enum):
    """
    Syndesi script commands enum
    """
    TERMINAL = "term"
    DRIVER = "driver"
    UI = "ui"


def main() -> None:
    """
    Main syndesi entry point
    """
    parser = argparse.ArgumentParser(
        prog="syndesi", description="Syndesi command line tool", epilog=""
    )

    parser.add_argument("--version", action="version", version=f"Syndesi {__version__}")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="-v = INFO, -vv = DEBUG"
    )
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument(
        "command",
        choices=[x.value for x in SyndesiCommand],
        help="Command, use syndesi <command> -h for help",
    )

    parser.add_argument("remaining", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)

    args = parser.parse_args()
    command = SyndesiCommand(args.command)

    if args.quiet:
        debug_level = logging.CRITICAL
    else:
        debug_levels = [logging.WARNING, logging.INFO, logging.DEBUG]
        debug_level = debug_levels[min(args.verbose, len(debug_levels) - 1)]

    logging.basicConfig(level=debug_level)

    try:
        if command == SyndesiCommand.TERMINAL:
            Terminal(args.remaining).run()
        elif command == SyndesiCommand.DRIVER:
            ...
        elif command == SyndesiCommand.UI:
            if find_spec("PySide6") is None:
                raise ImportError(
                    "Missing optional dependency 'PySide6'. Install with:\n"
                    "  python -m pip install syndesi[ui]"
                )
            #pylint: disable=import-outside-toplevel
            from syndesi.ui.app import main as start_ui

            start_ui(args.remaining)
        else:
            raise NotImplementedError(f"Command '{command.value}' is not supported yet")
    except KeyboardInterrupt:
        ...


if __name__ == "__main__":
    main()
