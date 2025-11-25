# File : syndesi_backend.py
# Author : Sébastien Deriaz
# License : GPL
"""
Main syndesi-backend CLI script
"""


import argparse
from enum import StrEnum

from ..cli.backend_console import BackendConsole
from ..cli.backend_status import BackendStatus
#from ..cli.backend_wrapper import BackendWrapper
from ..adapters.backend.backend import main as backend_main

class Command(StrEnum):
    """
    Syndesi-backend commands enum
    """
    STATUS = 'status'
    CONSOLE = 'console'
    START = 'start'

def main() -> None:
    """
    Main syndesi-backend entry point
    """
    argument_parser = argparse.ArgumentParser(prog="syndesi-backend", add_help=False)

    argument_parser.add_argument(
        "command",
        nargs="?",
        choices=list(Command),
        help='Command to run'
    )

    args, remaining_args = argument_parser.parse_known_args()

    if args.command is None:
        argument_parser.print_help()
        return

    if args.command == Command.STATUS:
        status = BackendStatus(remaining_args)
        status.run()
    elif args.command == Command.CONSOLE:
        console = BackendConsole(remaining_args)
        console.run()
    elif args.command == Command.START:
        backend_main(remaining_args)
    else:
        print(f'Invalid command : {args.command}')


if __name__ == "__main__":
    main()
