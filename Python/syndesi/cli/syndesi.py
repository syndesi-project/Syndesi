#!/usr/bin/env python

# Syndesi CLI
import argparse
from enum import Enum
from syndesi.cli.shell import ShellPrompt

class SubCommands(Enum):
    SHELL = 'shell'
   
def main():
    parser = argparse.ArgumentParser(
        prog='syndesi',
        description='Syndesi command line interface',
        epilog='')
    # Parse subcommand
    parser.add_argument('subcommand', choices=[SubCommands.SHELL.value])

    args, extra_args = parser.parse_known_args()

    if args.subcommand == SubCommands.SHELL.value:
        p = ShellPrompt()
        if len(extra_args):
            p.cmdqueue.append(' '.join(extra_args))
        p.cmdloop()
        


if __name__ == '__main__':
    main()