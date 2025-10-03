import argparse
from contextlib import nullcontext

from rich.console import Console

from syndesi.adapters.backend.backend import Backend
from syndesi.tools.backend_api import BACKEND_PORT, LOCALHOST


class BackendWrapper:
    def __init__(self, remaining_args: list[str]) -> None:
        argument_parser = argparse.ArgumentParser()

        argument_parser.add_argument(
            "-a",
            "--address",
            type=str,
            default=LOCALHOST,
            help="Listening address, set it to the interface that will be used by the client",
        )
        argument_parser.add_argument("-p", "--port", type=int, default=BACKEND_PORT)
        argument_parser.add_argument(
            "-s",
            "--shutdown-delay",
            type=int,
            default=None,
            help="Delay before the backend shutdowns automatically",
        )
        argument_parser.add_argument(
            "-q", "--quiet", default=False, action="store_true"
        )
        argument_parser.add_argument(
            "-v", "--verbose", default=False, action="store_true"
        )

        args = argument_parser.parse_args(remaining_args)

        self.address = args.address
        self.port = args.port
        self.shutdown_delay = args.shutdown_delay
        self.quiet = args.quiet
        self.verbose = args.verbose

    def run(self) -> None:
        console = Console()
        with (
            console.status(
                f"[bold green]Syndesi backend running on {self.address}", spinner="dots"
            )
            if not self.quiet
            else nullcontext()
        ):
            backend = Backend(
                host=self.address,
                port=self.port,
                backend_shutdown_delay=self.shutdown_delay,
            )
            try:
                backend.start()
            except KeyboardInterrupt:
                pass
