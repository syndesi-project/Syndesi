# shell.py
# Sébastien Deriaz
# 30.04.2024
from enum import Enum
from cmd import Cmd
from syndesi.adapters import *
import argparse
import shlex
import sys
import os

class ShellPrompt(Cmd):
    prompt = '❯ '
    intro = "Welcome to the Syndesi Shell! Type ? to list commands"
    #def __init__(self, completekey=..., stdin=..., stdout=...) -> None:
    #    super().__init__(completekey, stdin, stdout)
    #    self._adapter = None

    def do_exit(self, inp):
        print("Bye !")
        return True
    
    def do_serial(self, inp):
        print("Opening serial port...")
        self._adapter = SerialPort(**SerialPort.shell_parse(inp))

    def do_ip(self, inp):
        parser = argparse.ArgumentParser()
        parser.add_argument('-p', '--port', type=int, required=True)
        parser.add_argument('--ip', type=str, required=True)
        parser.add_argument('-t', '--transport', type=str, choices=['UDP', 'TCP'], default='TCP', required=False)
        try:
            args = parser.parse_args(shlex.split(inp))
        except SystemExit as e:
            pass
        else:
            self._adapter = IP(address=args.ip, port=args.port, transport=args.transport)

    def default(self, inp):
        if hasattr(self, '_adapter'):
            cmd = inp + '\n'
            output = self._adapter.query(cmd)
            print(output)
        else:
            print("no adapter !")

    def do_clear(self, _):
        if sys.platform == "linux" or sys.platform == "linux2" or sys.platform == "darwin":
            # linux
            os.system('clear')
        elif sys.platform == "win32":
            # Windows
            os.system('cls')

    def do_cls(self, _):
        self.do_clear()

    do_EOF = do_exit # Allow CTRL+d to exit 