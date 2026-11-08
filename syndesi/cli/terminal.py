# File : adapter_shell.py
# Author : Sébastien Deriaz
# License : GPL
"""
Syndesi shell, used to communicate with adapters, protocols and drivers directly
"""

import argparse
import ast
import logging
import math
from collections.abc import Sequence
from enum import Enum
from typing import Any

from syndesi.adapters.adapter import Adapter
from syndesi.adapters.events import AdapterClosedEvent, AdapterFrameEvent, SyndesiEvent
from syndesi.adapters.stop_conditions import FragmentSC

from ..adapters.ip import IP
from ..adapters.serialport import SerialPort
from ..adapters.visa import Visa
from ..tools.errors import AdapterOpenError
from .console import Shell

HISTORY_FILE_NAME = "syndesi"

class Format(Enum):
    """
    Display format
    """
    RAW = "raw"
    HEX = "hex"
    BYTES = "bytes"


FORMAT_DESCRIPTION = {
    Format.RAW : "Raw text, no substitutions",
    Format.BYTES: "Use Python bytes display syntax",
    Format.HEX: "Hex bytes either space separated or joined",
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
    SpecialLineEnding.CR: b"\r",
    SpecialLineEnding.LF: b"\n",
    SpecialLineEnding.CRLF: b"\r\n",
}

def hex2array(raw: str) -> bytes:
    """
    Convert hex to bytes

    00 01 0A FF -> b'\\x00\\x01\\x0a\\xff'

    00010AFF -> b'\\x00\\x01\\x0a\\xff'
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
    b'\\x00\\x01\\x0a\\xff' -> 00 01 0A FF
    """
    return " ".join([f"{x:02X}" for x in array])

def bytes_format_encode(text : str) -> bytes:
    """Convert string in python's bytes format to bytes"""
    output = ast.literal_eval(f"b'{text}'")
    if not isinstance(output, bytes):
        raise ValueError(f"Could not encode '{text}'")
    return output

def bytes_format_decode(data : bytes) -> str:
    """Convert bytes object to string representation using python's bytes formatting"""
    return str(data)[2:-1]

def parse_termination_argument(arg: str | None) -> bytes:
    """
    Convert line termination argument to a real \\n or \\r character
    """
    replace_list = [
        (b'\\n', b'\n'),
        (b'\\r', b'\r'),
        (b'\\t', b'\t')
    ]
    if arg is None:
        return b""
    # Return a special line end char if it corresponds
    for s, t in LINE_ENDING_CHARS.items():
        if arg == s.value:
            return t
    # Otherwise, encode and parse "\\n" -> "\n"
    raw_arg = arg.encode('utf-8')
    for source, dest in replace_list:
        raw_arg = raw_arg.replace(source, dest)
    return raw_arg

class ListSerialPortsAction(argparse.Action):
    """List serial ports action"""

    #nargs = 0
    const = True
    default = False
    required = False
    # def __init__(self,
    #              option_strings : Sequence[str],
    #              dest : str,
    #              default : bool = False,
    #              required : bool = False,
    #              help : Any | None = None
    #     ) -> None:
    #     super().__init__(
    #         option_strings=option_strings,
    #         dest=dest,
    #         nargs=0,
    #         const=True,
    #         default=default,
    #         required=required,
    #         help=help,
    #     )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[str] | None,
        option_string: str | None = None,
    ) -> None:
        ports = SerialPort.list_ports()
        for port in ports:
            print(f"{port}")
        parser.exit()

class Terminal:
    """
    Adapter shell, allows direct communication with an adapter
    """

    DEFAULT_TERMINATION = "\n"

    # pylint: disable=too-many-statements too-many-branches
    def __init__(self, input_arguments: list[str]) -> None:
        logging.basicConfig(level=logging.CRITICAL + 1)
        self._parser = argparse.ArgumentParser(prog="syndesi term")

        # Options shared by every adapter, added to each adapter subparser
        # through parents=[common] so they show up in "syndesi term <adapter> -h"
        common = argparse.ArgumentParser(add_help=False)
        common_group = common.add_argument_group("Terminal options")
        self._add_common_arguments(common_group)

        adapter_parsers = self._parser.add_subparsers(
            title="Adapter", help="Adapter", required=True, dest="adapter"
        )
        # IP
        ip_parser = adapter_parsers.add_parser(
            AdapterType.IP.value, help="IP Adapter", parents=[common]
        )
        ip_parser.add_argument("address", type=str)
        ip_parser.add_argument("port", type=int)
        ip_parser.add_argument(
            "--protocol", choices=["TCP", "UDP"], default="TCP"
        )
        # SerialPort
        serialport_parser = adapter_parsers.add_parser(
            AdapterType.SERIAL.value, help="SerialPort Adapter", parents=[common]
        )
        serialport_parser.add_argument("port", type=str)
        serialport_parser.add_argument("baudrate", type=int)
        serialport_parser.add_argument(
            "--rtscts", action="store_true", default=False, help="Enable RTS/CTS"
        )
        serialport_parser.add_argument(
            "--list",
            action=ListSerialPortsAction,
            nargs=0,
            default=False,
            help="List available serial ports",
        )
        # VISA
        visa_parser = adapter_parsers.add_parser(
            AdapterType.VISA.value, help="VISA Adapter", parents=[common]
        )
        visa_parser.add_argument("descriptor", type=str)

        # Parse the arguments and create the terminal
        args = self._parser.parse_args(input_arguments)

        try:
            timeout_arg = float(args.timeout)
        except ValueError as e:
            raise ValueError(f"Invalid timeout : {args.timeout}") from e

        if math.isnan(timeout_arg):
            timeout = None
        else:
            timeout = timeout_arg

        self.adapter: Adapter[Any, Any]
        # Create the adapter
        adapter = AdapterType(args.adapter)
        if adapter == AdapterType.IP:
            self.adapter = IP(
                address=args.address,
                port=args.port,
                transport=args.protocol,
                timeout=timeout,
                auto_open=False,
                stop_conditions=FragmentSC()
            )
        elif adapter == AdapterType.SERIAL:
            self.adapter = SerialPort(
                port=args.port,
                baudrate=args.baudrate,
                timeout=timeout,
                rts_cts=args.rtscts,
                auto_open=False,
                stop_conditions=FragmentSC()
            )
        elif adapter == AdapterType.VISA:
            self.adapter = Visa(
                descriptor=args.descriptor,
                timeout=timeout,
                auto_open=False,
                stop_conditions=FragmentSC()
            )

        self._termination = parse_termination_argument(args.term)

        self.adapter.register_event_callback(self.event)

        # Create the shell
        self.shell = Shell(
            on_command=self.on_command,
            history_file_name=HISTORY_FILE_NAME,
            commands=[],
        )

        self._format = Format(args.format)

    @staticmethod
    def _add_common_arguments(group: argparse._ArgumentGroup) -> None:
        """
        Add the options shared by every adapter (timeout, termination, format, ...)
        """
        group.add_argument(
            "-t",
            "--timeout",
            type=float,
            required=False,
            default=2.0,
            help="Adapter timeout (response)",
        )
        group.add_argument(
            "--term",
            required=False,
            default=SpecialLineEnding.LF.value,
            help="Termination, cr, lf, crlf or a custom string. Ignored with hex format"
        )
        group.add_argument(
            "-f",
            "--format",
            default=Format.BYTES.value,
            help="Format, text or hex",
            choices=[x.value for x in Format],
        )

    def run(self) -> None:
        """
        Main adapter loop
        """

        try:
            self.adapter.open()
            #self.protocol.open()
        except AdapterOpenError:
            self.shell.print(f"Failed to open {self.adapter}")
        else:
            self.shell.run()
            self.shell.print(
                f"Opened adapter {self.adapter.descriptor}",
                style=Shell.Style.NOTE,
            )

    def on_command(self, command: str) -> None:
        """
        Action to perform when a command is received
        """
        try:
            if self._format == Format.HEX:
                data = hex2array(command)
            elif self._format == Format.BYTES:
                data = bytes_format_encode(command)
            elif self._format == Format.RAW:
                data = command.encode('utf-8')
            else:
                raise RuntimeError("Invalid format")
        except ValueError:
            self.shell.print(f"Cannot parse '{command}'", Shell.Style.ERROR)
        else:
            self.adapter.write(data + self._termination)

    def on_frame(self, data : bytes) -> None:
        """On reception of adapter frame data"""

        if self._format == Format.HEX:
            text = array2hex(data)
        elif self._format == Format.BYTES:
            text = bytes_format_decode(data)
        elif self._format == Format.RAW:
            text = data.decode('utf-8')
        else:
            raise RuntimeError("Invalid format")

        self.shell.print(text)

    def _open_answer(self, answer: str) -> None:
        """
        Open the protocol on "y" answer or stop the shell otherwise
        """
        if answer.lower() == "y":
            # try:
            self.adapter.open()
        else:
            # Set the stop flag, exit will be effective on reprompt
            self.shell.stop()
        self.shell.reprompt()

    def event(self, event: SyndesiEvent) -> None:
        """
        Method called when an event is recevied from the adapter
        """
        if isinstance(event, AdapterClosedEvent):
            self.shell.ask("Adapter closed, reconnect ? [y/n]: ", self._open_answer)
        elif isinstance(event, AdapterFrameEvent):
            self.on_frame(event.frame.data)
