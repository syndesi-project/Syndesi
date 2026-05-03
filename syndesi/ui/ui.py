# File : ui.py
# Author : Sébastien Deriaz
# License : GPL
"""
Syndesi UI
"""

import asyncio
from enum import StrEnum
import argparse
import importlib
import dearpygui.dearpygui as dpg # type: ignore[import-untyped]
from .dearpygui_async import DearPyGuiAsync

import importlib.resources

from .tools import Block
from .adapter import IPBlock

CLASS_NAME_SEPARATOR = ':'

dpg_async = DearPyGuiAsync()

loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

# Dearpygui icons with DejaVuSans font
# ✗ ▲
# ● ○ ◆ ◇ ▲ △ ■ □
# ← → ↑ ↓ ↔ ⇒ ⇐ ⇑ ⇓ ➔

class UIBase:
    """Main UI window"""
    def __init__(
            self,
            width : int = 600,
            height : int = 800
        ) -> None:
        self._width = width
        self._height = height
        self._build()
        self._blocks : list[Block] = []

    def start(self) -> None:
        """Start the UI"""
        with dpg.font_registry():
            with importlib.resources.path("syndesi.fonts", "DejaVuSans.ttf") as f:
                with dpg.font(str(f), 16) as font:
                    dpg.bind_font(font)

        dpg.show_viewport()

        dpg_async.run()
        dpg.destroy_context()
    
    def _build(self) -> None:
        dpg.create_context()
        dpg.create_viewport(
            title="Syndesi UI", 
            width=self._width,
            height=self._height
        )
        
        self.window = dpg.add_window(
            width=self._width,
            height=self._height,
            no_resize=True,
            no_title_bar=True
        )

        dpg.set_primary_window(self.window, True)

        dpg.setup_dearpygui()

        

    def add_block(self, block : Block) -> None:
        """Add a display block to the window"""
        block.build(self.window)
        self._blocks.append(block)

class Command(StrEnum):
    """Syndesi ui CLI mode"""
    DRIVER_MODULE = 'module'
    DRIVER_PATH = 'path'
    IP = 'ip'
    SERIAL = 'serial'
    VISA = 'visa'
    MODBUS = 'modbus'
    DELIMTIED = 'delimited'

COMMAND_HELP = """The type of UI to open. Choose between :

- 'module' : Open a driver with dot location like package.module.driver:DriverClass
- 'path' : Open a driver with a path to the file like ./folder/driver.py:DriverClass
- 'ip' : Open an IP adapter
- 'serial' : Open a SerialPort adapter
- 'visa' : Open a VISA Adapter
- 'modbus' : Open a Modbus protocol
- 'delimited' : Open a Delimited protocol
"""

def main(args : list[str] | None = None) -> None:
    """Main Syndesi UI entry-point"""
    parser = argparse.ArgumentParser()

    #parser.add_argument("--verbose", "-v", action="count", default=0, help="-v = INFO, -vv = DEBUG")
    #debug_levels = [logging.WARNING, logging.INFO, logging.DEBUG]
    #parser.add_argument('command', choices=list(Command), type=str)
    subarsers = parser.add_subparsers(dest='command')



    # Driver module
    driver_module_parser = subarsers.add_parser(Command.DRIVER_MODULE.value, help=COMMAND_HELP)
    driver_module_parser.add_argument('module', help="Module location")

    # Driver path
    driver_path_parser = subarsers.add_parser(Command.DRIVER_PATH.value)
    driver_path_parser.add_argument('path', help="Driver path")

    # IP
    ip_parser = subarsers.add_parser(Command.IP.value)
    # ip_parser.add_argument('address', help="IP address")
    # ip_parser.add_argument('port', help="IP port")

    # Serial
    serial_parser = subarsers.add_parser(Command.SERIAL.value)
    # serial_parser.add_argument("port", help="Serial port")
    # serial_parser.add_argument("")

    #parser.add_argument('argument', type=str, help="The mode argument, see the mode help")

    arguments = parser.parse_args(args=args)

    

    command = Command(arguments.command)

    ui = UIBase()
    # if command == Command.DRIVER_MODULE:
    #     module, class_name = argument.split(CLASS_NAME_SEPARATOR)
    #     m = importlib.import_module(module)
    #     c = getattr(m, class_name)
    #     ui = UIDriver(c)
    # elif command == Command.DRIVER_PATH:
    #     path, class_name = argument.split(CLASS_NAME_SEPARATOR)
    #     m = importlib.util.spec_from_file_location(path)
    #     c = getattr(m, class_name)
    #     ui = UIDriver(c)
    if command == Command.IP:
        ui.add_block(IPBlock())
    # elif command == Command.PROTOCOL:
    #     protocol_name = Protocol(argument)
    #     if protocol_name == Protocol.DELIMTIED:
    #         protocol = Delimited
    #     elif protocol_name == Protocol.MODBUS:
    #         protocol = Modbus
    #     ui = UIProtocol(protocol)
    
    ui.start()

if __name__ == '__main__':
    main()