from .command import Command, Argument, Mode
import argparse
from ..adapters.timeout import Timeout
from ..adapters.ip import IP
from ..adapters.adapter import Adapter
from ..adapters.serialport import SerialPort
from ..protocols.delimited import Delimited
from enum import Enum
from cmd import Cmd
import sys
import os
from ..version import __version__
from colorist import ColorRGB

class Kind(Enum):
    IP = 'ip'
    SERIAL = 'serial'

TIMEOUT_ARGUMENT = Argument('-t', '--timeout', nargs='+', type=float, required=False, default=5, help='Adapter timeout (response)')
END = Argument('-e', '--end', required=False, default='\n', help='Termination')
MODE_ARGUMENT = Argument('-m', '--mode', choices=[x.value for x in Mode], default=Mode.COMMAND)

class AdapterShell(Cmd):
    __hiden_methods = ('do_EOF','do_clear','do_cls')
    #prompt = f'❯ '
    PROMPT_COLOR = ColorRGB(28, 90, 145)
    prompt = f'{PROMPT_COLOR}❯ {PROMPT_COLOR.OFF}'

    def __init__(self, adapter : Adapter) -> None:
        super().__init__()
        self._adapter = adapter
    def get_names(self):
        return [n for n in dir(self.__class__) if n not in self.__hiden_methods]

    def do_exit(self, inp):
        """Exit"""
        return True

    def default(self, inp):
        cmd = inp
        output = self._adapter.query(cmd)
        print(output)

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

class AdapterCommand(Command):
    def __init__(self, kind : str) -> None:
        super().__init__()
        MODE_ARGUMENT.add_to_parser(self._parser)
        TIMEOUT_ARGUMENT.add_to_parser(self._parser)

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

        # Open the adapter
        if self._kind == Kind.IP:
            self._adapter = Delimited(IP(address=args.address, port=args.port, transport=args.protocol, timeout=timeout))
        elif self._kind == Kind.SERIAL:
            self._adapter = Delimited(SerialPort(port=args.port, baudrate=args.baudrate, timeout=timeout))


        shell = AdapterShell(self._adapter)
        shell.intro = f"Connected to {self._adapter}"
        # Enter the shell
        try:
            shell.cmdloop()
        except KeyboardInterrupt:
            pass
