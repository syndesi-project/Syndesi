#from .command import Command, Argument, Mode
from argparse import ArgumentParser
from ..adapters.timeout import Timeout, TimeoutException
from ..adapters.ip import IP
from ..adapters.adapter import Adapter
from ..adapters.serialport import SerialPort
from ..protocols.delimited import Delimited
from ..protocols.raw import Raw
from enum import Enum
from cmd import Cmd
import sys
import os
from ..version import __version__
try:
    from colorist import ColorRGB
    COLORIST_AVAILABLE = True
except ImportError:
    COLORIST_AVAILABLE = False
try:
    from colorama import Fore
    COLORAMA_AVAILABLE = True
except ImportError:
    COLORAMA_AVAILABLE = False

class Mode(Enum):
    COMMAND = 'command' # Command-like, write, read, write, read
    FLOW = 'flow' # Write and read at the same time

class Format(Enum):
    TEXT = 'text'
    HEX = 'hex'

class Argument:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def add_to_parser(self, parser : ArgumentParser):
        parser.add_argument(*self.args, **self.kwargs)

class Kind(Enum):
    IP = 'ip'
    SERIAL = 'serial'

class LineEnding(Enum):
    CR = 'cr'
    LF = 'lf'
    CRLF = 'crlf'
    NONE = 'none'

LINE_ENDING_CHARS = {
    LineEnding.CR : '\r',
    LineEnding.LF : '\n',
    LineEnding.CRLF : '\r\n',
    LineEnding.NONE : ''
}

TIMEOUT_ARGUMENT = Argument('-t', '--timeout', nargs='+', type=float, required=False, default=[2], help='Adapter timeout (response)')
END = Argument('-e', '--end', required=False, default=LineEnding.LF.value, help='Termination, cr, lf, crlf or none. Only used with text format', choices=[x.value for x in LineEnding])
MODE_ARGUMENT = Argument('-m', '--mode', choices=[x.value for x in Mode], default=Mode.COMMAND)
FORMAT_ARGUMENT = Argument('-f', '--format', default=Format.TEXT, help='Format, text or hex', choices=[x.value for x in Format])

def hex2array(raw : str):
    s = raw.replace(' ', '')
    if len(s) % 2 != 0:
        s = '0' + s
    try:
        array = bytes([int(s[2*i:2*(i+1)], 16) for i in range(len(s)//2)])
    except ValueError:
        raise ValueError(f'Cannot parse hex string : {raw}')
    return array

def array2hex(array : bytes):
    return ' '.join([f'{x:02X}' for x in array])

class AdapterCmd(Cmd):
    __hiden_methods = ('do_EOF','do_clear','do_cls')
    if COLORIST_AVAILABLE:
        PROMPT_COLOR = ColorRGB(28, 90, 145)
        prompt = f'{PROMPT_COLOR}❯ {PROMPT_COLOR.OFF}'
    elif COLORAMA_AVAILABLE:
        prompt = f'{Fore.CYAN}❯{Fore.RESET} '
    else:
        prompt = f'❯ '

    def __init__(self, adapter : Adapter, _format : Format) -> None:
        super().__init__()
        self._adapter = adapter
        self._format = _format

    def get_names(self):
        return [n for n in dir(self.__class__) if n not in self.__hiden_methods]

    def do_exit(self, inp):
        """Exit"""
        return True

    def default(self, inp):
        # TODO : Add flow mode here, manage it somehow, maybe not with AdapterCmd ? Maybe with a more custom one ?
        if self._format == Format.TEXT:
            # Send the data directly
            cmd = inp
        elif self._format == Format.HEX:
            # Parse it, remove spaces, convert to int
            cmd = hex2array(inp)

        try:
            output = self._adapter.query(cmd)
        except TimeoutException:
            printed_output = ''
        else:
            if self._format == Format.TEXT:
                printed_output = output
            elif self._format == Format.HEX:
                printed_output = array2hex(output)

        print(printed_output)

    def do_clear(self, _):
        if sys.platform == "linux" or sys.platform == "linux2" or sys.platform == "darwin":
            # linux
            os.system('clear')
        elif sys.platform == "win32":
            # Windows
            os.system('cls')

    def do_cls(self, _):
        self.do_clear()

    def do_help(self, arg: str) -> bool | None:
        if arg:
            # Use Cmd's help
            super().do_help(arg)
        else:
            # Otherwise, print a custom help
            names = self.get_names()

            cmds_doc = []
            cmds_undoc = []
            docs = []
            topics = set()
            for name in names:
                if name[:5] == 'help_':
                    topics.add(name[5:])
            names.sort()
            # There can be duplicates if routines overridden
            prevname = ''
            for name in names:
                if name[:3] == 'do_':
                    if name == prevname:
                        continue
                    prevname = name
                    cmd=name[3:]
                    if cmd in topics:
                        #cmds_doc.append(cmd)
                        topics.remove(cmd)
                    elif getattr(self, name).__doc__:
                        cmds_doc.append(cmd)
                        docs.append(getattr(self, name).__doc__)
                    else:
                        cmds_undoc.append(cmd)

            print(f"Syndesi shell V{__version__}")
            print("Available commands :")
            max_width = max([len(cmd) for cmd in cmds_doc])
            for cmd, doc in zip(cmds_doc, docs):
                print(f"  {cmd:<{max_width+2}} : {doc}")

            #self.print_topics(self.misc_header,  sorted(topics),15,80)
            #self.print_topics(self.undoc_header, cmds_undoc, 15,80)

    do_EOF = do_exit # Allow CTRL+d to exit

class AdapterShell:
    def __init__(self, kind : str) -> None:
        self._parser = ArgumentParser()
        MODE_ARGUMENT.add_to_parser(self._parser)
        TIMEOUT_ARGUMENT.add_to_parser(self._parser)
        END.add_to_parser(self._parser)
        FORMAT_ARGUMENT.add_to_parser(self._parser)

        self._kind = Kind(kind)
        if self._kind == Kind.IP:
            self._parser.add_argument('-a', '--address', type=str, required=True)
            self._parser.add_argument('-p', '--port', type=int, required=True)
            self._parser.add_argument('--protocol', choices=['TCP', 'UDP'], default='TCP')
        elif self._kind == Kind.SERIAL:
            self._parser.add_argument('-p', '--port', type=str, required=True)
            self._parser.add_argument('-b', '--baudrate', type=int, required=True)
        else:
            raise ValueError('Unsupported Kind')

    def run(self, remaining_args):
        args = self._parser.parse_args(remaining_args)

        timeout = Timeout(args.timeout)

        # Create the adapter
        if self._kind == Kind.IP:
            adapter = IP(address=args.address, port=args.port, transport=args.protocol, timeout=timeout)
        else:
            adapter = SerialPort(port=args.port, baudrate=args.baudrate, timeout=timeout)

        adapter.set_default_timeout(Timeout(on_response='return'))

        # Add the protocol
        _format = Format(args.format)
        if _format == Format.HEX:
            self._protocol = Raw(adapter)
        elif _format == Format.TEXT:
            line_ending = LINE_ENDING_CHARS[LineEnding(args.end)]
            self._protocol = Delimited(adapter, termination=line_ending)

        shell = AdapterCmd(self._protocol, _format)
        shell.intro = f"Connected to {self._protocol}"
        # Enter the shell
        try:
            shell.cmdloop()
        except KeyboardInterrupt:
            pass
