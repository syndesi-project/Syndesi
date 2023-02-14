"""
C++ code generation class
"""

from commands import Command
from os.path import join, dirname
from utilities import replace_str
#from settings import types
from typing import List
from tabulate import tabulate

TAB = 4*' '

class MD():
    def __init__(self, commands_list  : List[Command]):
        """
        Instanciate a markdown code generation class with a list of Command objects
        """
        self._commands = commands_list

    def commands_list(self):
        """
        Outputs a list of commands formatted as markdown text
        """

        output = ""

        for command in self._commands:
            # Title
            output += f"## {command.alias}\n\n"
            # Request
            output += f"### Request\n\n"
            if command.has_request:
                output += tabulate([["A", "B"], ["C", "D"]])



            else:
                output += "This command cannot be used as a request\n\n"
            # Reply 
            output += f"### Reply\n\n"
            if command.has_reply:
                output += "has reply\n\n"
            else:
                output += "This command cannot be used as a reply\n\n"

        return output


            





