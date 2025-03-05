#!/usr/bin/env python

# Syndesi CLI
import argparse
from enum import Enum
from ..version import __version__
from .shell import AdapterShell
from typing import Dict
from ..tools.log import log_settings

class Commands(Enum):
    SERIAL = 'serial'
    IP = 'ip'
    MODBUS = 'modbus'

DESCRIPTION = {
    Commands.SERIAL : 'Open a live serialport shell',
    Commands.IP : 'Open a live ip shell',
    Commands.MODBUS : 'Open a live modbus shell'
}

def main():
    parser = argparse.ArgumentParser(
        prog='syndesi',
        description='Syndesi command line tool',
        epilog='')
    
    parser.add_argument('--version', action='version',
                    version=f'%(prog)s {__version__}')
    parser.add_argument('-v', '--verbose', action='store_true')
    parser.add_argument('command', choices=[x.value for x in Commands], help='Command, use syndesi <command> -h for help')

    args, remaining_args = parser.parse_known_args()
    command = Commands(args.command)

    if args.verbose:
        log_settings('DEBUG', console=True)
        

    if command == Commands.SERIAL:
        AdapterShell('serial').run(remaining_args)
    elif command == Commands.IP:
        AdapterShell('ip').run(remaining_args)
    else:
        raise RuntimeError(f"Command '{command.value}' is not supported yet")

if __name__ == '__main__':
    main()