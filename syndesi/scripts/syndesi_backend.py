# File : syndesi_backend.py
# Author : Sébastien Deriaz
# License : GPL

import argparse

from ..cli.backend_console import BackendConsole
from ..cli.backend_status import BackendStatus
from ..cli.backend_wrapper import BackendWrapper


def main() -> None:
    argument_parser = argparse.ArgumentParser(prog="syndesi-backend")

    argument_parser.add_argument(
        "--status", action="store_true", help="Show backend status"
    )

    argument_parser.add_argument(
        "--console", action="store_true", help="Run backend console"
    )

    args, remaining_args = argument_parser.parse_known_args()

    if args.status:
        status = BackendStatus(remaining_args)
        status.run()
    elif args.console:
        console = BackendConsole(remaining_args)
        console.run()
    else:
        backend = BackendWrapper(remaining_args)
        backend.run()


if __name__ == "__main__":
    main()
