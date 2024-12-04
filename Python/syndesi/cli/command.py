from argparse import ArgumentParser
from enum import Enum

class Argument:
    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs

    def add_to_parser(self, parser : ArgumentParser):
        parser.add_argument(*self.args, **self.kwargs)

END = Argument('-e', '--end', required=False, default='\n', help='Termination')

class Mode(Enum):
    COMMAND = 'command'
    HEX = 'hex'

MODE_ARGUMENT = Argument('-m', '--mode', choices=[x.value for x in Mode], default=Mode.COMMAND)
# HEX / command line mode ?
# In HEX mode it would be nice to accept both 0A12BC10 etc... and 0A 12 BC 10 input (and return accordingly)
# Also it could be nice to fuse serial and ip commands in one because they are kind of the same, they are going to listen for data and use an adapter

class Command:
    def __init__(self) -> None:
        self._parser = ArgumentParser()
    def run(self, remaining_args):
        raise NotImplementedError()


