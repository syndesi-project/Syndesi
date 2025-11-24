# File : syndesi_backend.py
# Author : Sébastien Deriaz
# License : GPL

import argparse

from ..cli.backend_console import BackendConsole
from ..cli.backend_status import BackendStatus
#from ..cli.backend_wrapper import BackendWrapper
from ..adapters.backend.backend import main as backend_main


def main() -> None:
    argument_parser = argparse.ArgumentParser(prog="syndesi-backend")

    argument_parser.add_argument(
        "--status", action="store_true", help="Show backend status"
    )

    argument_parser.add_argument(
        "--console", action="store_true", help="Run backend console"
    )

    argument_parser.add_argument(
        "--start", action="store_true", help="Start the backend"
    )

    args, remaining_args = argument_parser.parse_known_args()

    print(args)

    if args.status:
        status = BackendStatus(remaining_args)
        status.run()
    elif args.console:
        console = BackendConsole(remaining_args)
        console.run()
    else:
        backend_main(remaining_args)
        #backend = BackendWrapper(remaining_args)
        #backend.run()
TODO : Make this work without the wrapper and make clean so as to have a help for the syndesi-backend command and also get help for the backend itself (--address, --port, etc...)


if __name__ == "__main__":
    main()
