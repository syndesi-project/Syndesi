# shell.py
# Sébastien Deriaz
# 30.04.2024
from enum import Enum
from cmd import Cmd
from ..adapters import *
from ..protocols import Delimited
from ..tools.log import set_log_file, set_log_level, LoggerAlias
import argparse
import logging
import shlex
import sys
import os
#from colorist import ColorRGB

VERSION = 0.1

class ShellPrompt(Cmd):
    _logger = logging.getLogger(LoggerAlias.CLI.value)
    __hiden_methods = ('do_EOF','do_clear','do_cls')
    #PROMPT_COLOR = ColorRGB(28, 90, 145)

    #prompt = f'{PROMPT_COLOR}❯ {PROMPT_COLOR.OFF}'
    prompt = f'❯ '
    intro = "Welcome to the Syndesi Shell! Type ? to list commands"

    common_parser = argparse.ArgumentParser(add_help=False)
    common_parser.add_argument('-v', '--verbose', help='Print logging informations', action='store_true', default=False)
    common_parser.add_argument('-d', '--debug', help='Print debug informations', action='store_true', default=False)
    common_parser.add_argument('--log-file', type=str, default='')

    def _parse_common_args(self, args):
        common_args, other_args = self.common_parser.parse_known_args(args)
        if common_args.debug:
            set_log_level('DEBUG')
        elif common_args.verbose:
            set_log_level('INFO')
        
        if common_args.log_file != '': # TODO : test this
            set_log_file(common_args.log_file)
        
        return other_args


    def get_names(self):
        return [n for n in dir(self.__class__) if n not in self.__hiden_methods]

    def do_exit(self, inp):
        """Exit"""
        return True
    
    def do_serial(self, inp):
        """Open serial adapter"""
        self._adapter = SerialPort(**SerialPort.shell_parse(inp))

    def do_ip(self, inp):
        """Open IP adapter with delimited protocol (\\n at the end of each line by default)"""
        arguments = shlex.split(inp)
        other_arguments = self._parse_common_args(arguments)

        parser = argparse.ArgumentParser(
            prog='ip'
        )
        parser.add_argument('ip', type=str)
        parser.add_argument('-p', '--port', type=int, required=True)
        parser.add_argument('-t', '--transport', type=str, choices=['UDP', 'TCP'], default='TCP', required=False)
        parser.add_argument('-e', '--end', help='Newline character, \\n by default, on unix systems, use -e \'\\\\n\' to circumvent backslash substitution', default='\n', required=False)
        try:
            args = parser.parse_args(other_arguments)
        except SystemExit as e:
            pass
        else:
            end_string : str = args.end
            termination = end_string.encode('utf-8').decode('unicode_escape')
            self._logger.debug(f'Opening Delimited IP with termination : {repr(termination)}')
            self._adapter = Delimited(IP(address=args.ip, port=args.port, transport=args.transport), termination=termination)
            self._adapter._adapter.open()
            print(f"Successfully opened IP adapter at {args.ip}:{args.port} ({repr(termination)} termination)")

    def default(self, inp):
        if hasattr(self, '_adapter'):
            cmd = inp
            output = self._adapter.query(cmd)
            print(output)
        else:
            print(f"Unknown command : {inp}, type ? to list commands")

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

            print(f"Syndesi shell V{VERSION}")
            print("Available commands :")
            max_width = max([len(cmd) for cmd in cmds_doc])
            for cmd, doc in zip(cmds_doc, docs):
                print(f"  {cmd:<{max_width+2}} : {doc}")

            #self.print_topics(self.misc_header,  sorted(topics),15,80)
            #self.print_topics(self.undoc_header, cmds_undoc, 15,80)

    do_EOF = do_exit # Allow CTRL+d to exit 