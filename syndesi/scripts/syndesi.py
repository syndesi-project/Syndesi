# File : syndesi.py
# Author : Sébastien Deriaz
# License : GPL

import argparse
from enum import Enum

from ..cli.shell import AdapterShell, AdapterType
from ..tools.log import log
from ..version import __version__


class SyndesiCommands(Enum):
    SERIAL = "serial"
    IP = "ip"
    MODBUS = "modbus"
    VISA = "visa"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="syndesi", description="Syndesi command line tool", epilog=""
    )

    parser.add_argument("--version", action="version", version=f"Syndesi {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument(
        "command",
        choices=[x.value for x in SyndesiCommands],
        help="Command, use syndesi <command> -h for help",
    )

    args, remaining_args = parser.parse_known_args()
    command = SyndesiCommands(args.command)

    if args.verbose:
        log("DEBUG", console=True)

    if command == SyndesiCommands.SERIAL:
        AdapterShell(AdapterType.SERIAL, remaining_args).run()
    elif command == SyndesiCommands.IP:
        AdapterShell(AdapterType.IP, remaining_args).run()
    elif command == SyndesiCommands.VISA:
        AdapterShell(AdapterType.VISA, remaining_args).run()
    else:
        raise RuntimeError(f"Command '{command.value}' is not supported yet")


if __name__ == "__main__":
    main()
