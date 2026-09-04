# File : syndesi.py
# Author : Sébastien Deriaz
# License : GPL
"""
Main syndesi CLI script
"""

import argparse
import logging
from enum import Enum

from ..cli.shell import AdapterShell, AdapterType

from ..version import __version__


class SyndesiCommands(Enum):
    """
    Syndesi script commands enum
    """
    SERIAL = "serial"
    IP = "ip"
    MODBUS = "modbus"
    VISA = "visa"
    UI = "ui"

def main() -> None:
    """
    Main syndesi entry point
    """
    parser = argparse.ArgumentParser(
        prog="syndesi", description="Syndesi command line tool", epilog=""
    )

    parser.add_argument("--version", action="version", version=f"Syndesi {__version__}")
    parser.add_argument("-v", "--verbose", action="count", default=0, help="-v = INFO, -vv = DEBUG")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument(
        "command",
        choices=[x.value for x in SyndesiCommands],
        help="Command, use syndesi <command> -h for help",
    )

    args, remaining_args = parser.parse_known_args()
    command = SyndesiCommands(args.command)

    if args.quiet:
        debug_level = logging.CRITICAL
    else:
        debug_levels = [logging.WARNING, logging.INFO, logging.DEBUG]
        debug_level = debug_levels[min(args.verbose, len(debug_levels)-1)]

    logging.basicConfig(level=debug_level)

    try:
        if command == SyndesiCommands.SERIAL:
            AdapterShell(AdapterType.SERIAL, remaining_args).run()
        elif command == SyndesiCommands.IP:
            AdapterShell(AdapterType.IP, remaining_args).run()
        elif command == SyndesiCommands.VISA:
            AdapterShell(AdapterType.VISA, remaining_args).run()
        elif command == SyndesiCommands.UI:
            try:
                from syndesi.ui.ui import main as start_ui
            except ImportError as e:
                raise ImportError(
                    "Missing optional dependency 'dearpygui'. Install with:\n"
                    "  python -m pip install syndesi[ui]"
                ) from e
            start_ui(remaining_args)
        else:
            raise NotImplementedError(f"Command '{command.value}' is not supported yet")
    except KeyboardInterrupt:
        ...


if __name__ == "__main__":
    main()
