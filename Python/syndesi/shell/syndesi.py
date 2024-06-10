#!/usr/bin/env python

# Syndesi CLI
import argparse
from cmd import Cmd
from enum import Enum

class MyPrompt(Cmd):
    prompt = '❯ '
    intro = "Welcome! Type ? to list commands"

    def do_exit(self, inp):
        print("Bye !")
        return True

    def do_connect(self, inp):
        print("Device")

    def default(self, inp):
        print(f"Entered : {inp}")


    do_EOF = do_exit # Allow CTRL+d to exit
 

class SubCommands(Enum):
    SHELL = 'shell'




def connect():
    print("Entering connect subcommand...")

    p = MyPrompt()
    p.cmdloop()




def main():
    parser = argparse.ArgumentParser(
        prog='syndesi',
        description='Syndesi command line interface',
        epilog='')
    # Parse subcommand    
    parser.add_argument('subcommand', choices=[SubCommands.SHELL.value])

    args = parser.parse_args()

    if args.subcommand == SubCommands.SHELL.value:
        connect()
        


if __name__ == '__main__':
    main()