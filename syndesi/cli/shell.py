# File : adapter_shell.py
# Author : Sébastien Deriaz
# License : GPL
"""
Syndesi shell, used to communicate with adapters, protocols and drivers directly
"""


import logging
from argparse import ArgumentParser
from enum import Enum
from typing import Any

from ..adapters.adapter import Adapter
from ..adapters.ip import IP
from ..adapters.serialport import SerialPort
from ..adapters.timeout import Timeout
from ..adapters.visa import Visa
from ..protocols.delimited import Delimited
from ..protocols.protocol import (
    Protocol,
    ProtocolDisconnectedEvent,
    ProtocolEvent,
    ProtocolFrameEvent,
)
from ..protocols.raw import Raw
from ..tools.errors import AdapterOpenError
from .console import Shell

HISTORY_FILE_NAME = "syndesi"

logging.basicConfig(level=logging.CRITICAL + 1)


class Format(Enum):
    """
    Display format
    """

    TEXT = "text"
    HEX = "hex"
    BYTES = "bytes"


FORMAT_DESCRIPTION = {
    Format.TEXT: "Encoded text",
    Format.HEX: "Hex bytes either space separated or joined",
    Format.BYTES: "Use Python bytes display syntax",
}


class AdapterType(Enum):
    """
    Adapter type enum
    """

    IP = "ip"
    SERIAL = "serial"
    VISA = "visa"


class SpecialLineEnding(Enum):
    """
    Line ending enum
    """

    CR = "cr"
    LF = "lf"
    CRLF = "crlf"


LINE_ENDING_CHARS = {
    SpecialLineEnding.CR: "\r",
    SpecialLineEnding.LF: "\n",
    SpecialLineEnding.CRLF: "\r\n",
}


def hex2array(raw: str) -> bytes:
    """
    Convert hex to bytes

    00 01 0A FF -> b'\x00\x01\x0a\xff'
    00010AFF -> b'\x00\x01\x0a\xff'
    """
    s = raw.replace(" ", "")
    if len(s) % 2 != 0:
        s = "0" + s
    try:
        array = bytes([int(s[2 * i : 2 * (i + 1)], 16) for i in range(len(s) // 2)])
    except ValueError as err:
        raise ValueError(f"Cannot parse hex string : {raw}") from err
    return array


def array2hex(array: bytes) -> str:
    """
    Convert bytes to hex string
    b'\x00\x01\x0a\xff' -> 00 01 0A FF
    """
    return " ".join([f"{x:02X}" for x in array])


def parse_end_argument(arg: str | None) -> str | None:
    """
    Convert line end argument to a real \\n or \\r character
    """
    if arg is None:
        return None
    # Return a special line end char if it corresponds
    for s, t in LINE_ENDING_CHARS.items():
        if arg == s.value:
            return t
    # Otherwise parse "\\n" -> "\n"
    return arg.replace("\\n", "\n").replace("\\r", "\r")


class AdapterShell:
    """
    Adapter shell, allows direct communication with an adapter
    """

    DEFAULT_TERMINATION = "\n"

    def __init__(self, kind: AdapterType, input_arguments: list[str]) -> None:

        self._parser = ArgumentParser()
        self._parser.add_argument(
            "-t",
            "--timeout",
            nargs="+",
            type=float,
            required=False,
            default=[2],
            help="Adapter timeout (response)",
        )
        self._parser.add_argument(
            "-e",
            "--end",
            required=False,
            default=SpecialLineEnding.LF.value,
            help="Termination, cr, lf, crlf, none or a custom string. "
            "Only used with text format. Custom receive end can be set with --receive-end",
        )
        self._parser.add_argument(
            "--receive-end",
            required=False,
            default=None,
            help="Reception termination, same as --end but for"
            "reception only. If not set, the value of --end will be used",
        )
        self._parser.add_argument(
            "-f",
            "--format",
            default=Format.TEXT,
            help="Format, text or hex",
            choices=[x.value for x in Format],
        )
        self._parser.add_argument(
            "--backend-address", default=None, help="Address of the backend server"
        )
        self._parser.add_argument(
            "--backend-port", default=None, help="Port of the backend server"
        )

        if kind == AdapterType.IP:
            self._parser.add_argument("address", type=str)
            self._parser.add_argument("port", type=int)
            self._parser.add_argument(
                "--protocol", choices=["TCP", "UDP"], default="TCP"
            )
        elif kind == AdapterType.SERIAL:
            self._parser.add_argument("port", type=str)
            self._parser.add_argument("baudrate", type=int)
            self._parser.add_argument(
                "--rtscts", action="store_true", default=False, help="Enable RTS/CTS"
            )
        elif kind == AdapterType.VISA:
            self._parser.add_argument("descriptor", type=str)
        else:
            raise ValueError("Unsupported Kind")
        args = self._parser.parse_args(input_arguments)

        timeout = Timeout(args.timeout)

        self.adapter: Adapter
        # Create the adapter
        if kind == AdapterType.IP:
            self.adapter = IP(
                address=args.address,
                port=args.port,
                transport=args.protocol,
                timeout=timeout,
                auto_open=False,
            )
        elif kind == AdapterType.SERIAL:
            self.adapter = SerialPort(
                port=args.port,
                baudrate=args.baudrate,
                timeout=timeout,
                rts_cts=args.rtscts,
                auto_open=False,
            )
        elif kind == AdapterType.VISA:
            self.adapter = Visa(descriptor=args.descriptor, timeout=timeout)

        self.adapter.set_default_timeout(Timeout(action="return_empty"))

        # Add the protocol
        _format = Format(args.format)
        self.protocol: Protocol[Any]
        if _format == Format.HEX:
            self.protocol = Raw(self.adapter, event_callback=self.event)
        elif _format == Format.TEXT:
            send_end = parse_end_argument(args.end)
            receive_end = parse_end_argument(args.receive_end)
            if send_end is None:
                send_end = self.DEFAULT_TERMINATION
            if receive_end is None:
                receive_end = send_end

            self.protocol = Delimited(
                self.adapter,
                termination=send_end,
                receive_termination=receive_end,
                event_callback=self.event,
            )

        # Create the shell
        self.shell = Shell(
            on_command=self.on_command,
            history_file_name=HISTORY_FILE_NAME,
            commands=[],
        )

    def run(self) -> None:
        """
        Main adapter loop
        """

        try:
            self.protocol.open()
        except AdapterOpenError:
            self.shell.print(f"Failed to open {self.adapter}")
        else:
            self.shell.run()
            self.shell.print(
                f"Opened adapter {self.adapter.descriptor}", style=Shell.Style.NOTE
            )

    def on_command(self, command: str) -> None:
        """
        Action to perform when a command is received
        """
        self.protocol.write(command)

    def _open_answer(self, answer: str) -> None:
        """
        Open the protocol on "y" answer or stop the shell otherwise
        """
        if answer.lower() == "y":
            # try:
            self.protocol.open()
        else:
            # Set the stop flag, exit will be effective on reprompt
            self.shell.stop()
        self.shell.reprompt()

    def event(self, event: ProtocolEvent) -> None:
        """
        Method called when an event is recevied from the adapter
        """
        if isinstance(event, ProtocolDisconnectedEvent):
            self.shell.ask(
                "Adapter disconnected, reconnect ? [y/n]: ", self._open_answer
            )
        elif isinstance(event, ProtocolFrameEvent):
            data = event.frame.get_payload()
            # TODO : Catch data from delimited with formatting
            self.shell.print(data)
