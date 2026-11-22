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

from ..adapters.hid import HID, HIDDescriptor
from ..adapters.i2c import I2C, I2CTransfer
from ..adapters.ip import IP
from ..adapters.serialport import SerialPort
from ..adapters.spi import SPI
from ..adapters.visa import Visa
from ..tools.errors import AdapterError, AdapterOpenError
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
    I2C = "i2c"
    SPI = "spi"
    HID = "hid"


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

class ListAction(argparse.Action):
    """
    Print what const() lists (serial ports, I2C buses, ...) and exit

    Added with nargs=0 and const set to the function that lists
    """

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[str] | None,
        option_string: str | None = None,
    ) -> None:
        for item in self.const():
            print(f"{item}")
        parser.exit()

def _list_hid_devices() -> list[str]:
    """The HID devices, with the path that opens each interface"""
    return [f"{device}  [{device.path}]" for device in HID.list_devices()]


def _hid_adapter(
    device: str, report_id: int, report_size: int | None, timeout: float | None
) -> HID:
    """HID adapter of a VID:PID[:SERIAL][@INTERFACE] string, or of a path"""
    string = device if device.startswith("hid:") else f"hid:{device}"
    try:
        descriptor = HIDDescriptor.from_string(string)
    except ValueError:
        descriptor = HIDDescriptor(path=device)
    return HID(
        descriptor.vendor_id,
        descriptor.product_id,
        serial_number=descriptor.serial_number,
        interface=descriptor.interface,
        path=descriptor.path,
        report_id=report_id,
        report_size=report_size,
        timeout=timeout,
        auto_open=False,
    )


class Terminal:
    """
    Adapter shell, allows direct communication with an adapter
    """

    DEFAULT_TERMINATION = "\n"

    # pylint: disable=too-many-statements too-many-branches too-many-locals
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
            action=ListAction,
            nargs=0,
            const=SerialPort.list_ports,
            default=False,
            help="List available serial ports",
        )
        # I2C and SPI, native buses only : a bridge is a driver, written in python
        i2c_parser = adapter_parsers.add_parser(
            AdapterType.I2C.value,
            help="I2C Adapter (Linux)",
            parents=[common],
            description="Each line is written to the device, followed by a read of "
            "--read bytes with a repeated start",
        )
        i2c_parser.add_argument("bus", type=str, help="/dev/i2c-N")
        i2c_parser.add_argument(
            "address", type=lambda x: int(x, 0), help="7-bit address, 0x48 or 72"
        )
        i2c_parser.add_argument(
            "-r",
            "--read",
            type=int,
            default=0,
            help="Bytes to read after each write, 0 to only write",
        )
        spi_parser = adapter_parsers.add_parser(
            AdapterType.SPI.value,
            help="SPI Adapter (Linux)",
            parents=[common],
            description="Each line is sent to the device, the bytes received meanwhile "
            "are printed",
        )
        spi_parser.add_argument("device", type=str, help="/dev/spidevB.C")
        for parser, lister, what in (
            (i2c_parser, I2C.list_buses, "I2C buses"),
            (spi_parser, SPI.list_buses, "SPI devices"),
        ):
            parser.add_argument(
                "--list",
                action=ListAction,
                nargs=0,
                const=lister,
                default=False,
                help=f"List available {what}",
            )
            # Binary buses : hex and no termination, unless asked otherwise
            parser.set_defaults(term="", format=Format.HEX.value)
        # HID
        hid_parser = adapter_parsers.add_parser(
            AdapterType.HID.value,
            help="HID Adapter",
            parents=[common],
            description="Each line is sent as an output report, every input report "
            "received is printed. Needs hidapi : pip install syndesi[hid]",
        )
        hid_parser.add_argument(
            "device", type=str, help="VID:PID, VID:PID:SERIAL (hex ids), or a path"
        )
        hid_parser.add_argument(
            "--report-id",
            type=lambda x: int(x, 0),
            default=0,
            help="Report id added in front of each report, 0 by default",
        )
        hid_parser.add_argument(
            "--report-size",
            type=int,
            default=None,
            help="Pad each report with zeros to this size (Windows needs full reports)",
        )
        hid_parser.add_argument(
            "--list",
            action=ListAction,
            nargs=0,
            const=_list_hid_devices,
            default=False,
            help="List available HID devices",
        )
        hid_parser.set_defaults(term="", format=Format.HEX.value)
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
        self._read_length = 0
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
        elif adapter == AdapterType.I2C:
            if args.read < 0:
                raise ValueError(f"Invalid read length : {args.read}")
            self._read_length = args.read
            self.adapter = I2C(args.bus, args.address, timeout=timeout, auto_open=False)
        elif adapter == AdapterType.SPI:
            self.adapter = SPI(args.device, timeout=timeout, auto_open=False)
        elif adapter == AdapterType.HID:
            self.adapter = _hid_adapter(
                args.device, args.report_id, args.report_size, timeout
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
            data += self._termination
            if self._read_length:
                data = I2CTransfer(data, self._read_length)
            try:
                self.adapter.write(data)
            except AdapterError as e:
                self.shell.print(str(e), Shell.Style.ERROR)

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
