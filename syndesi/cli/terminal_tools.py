# File : terminal_tools.py
# Author : Sébastien Deriaz
# License : GPL


class TerminalCompatible:
    name = "..."
    description = "..."
    help = "..."
    aliases = "..."
    # prompt settings ? color ?

    def handle_input(self, user_input: str | bytes) -> None:
        pass
