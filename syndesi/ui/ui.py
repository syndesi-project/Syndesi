# File : ui.py
# Author : Sébastien Deriaz
# License : GPL
"""
Syndesi UI
"""

import argparse
import asyncio
import importlib
import importlib.resources
from enum import StrEnum
from typing import Any, Tuple, Type, TypeVar, overload

import dearpygui.dearpygui as dpg #type: ignore

from syndesi.adapters.adapter import Adapter
from syndesi.adapters.bytesadapter import BytesAdapter
from syndesi.adapters.ip import IP
from syndesi.adapters.serialport import SerialPort
from syndesi.component import Component, Event
from syndesi.drivers.driver import Driver
from syndesi.protocols.delimited import Delimited
from syndesi.protocols.protocol import Protocol
from syndesi.tools.errors import AdapterOpenError
from syndesi.ui.protocol import DelimitedBlock, ProtocolBlock

from .adapter import BytesAdapterBlock, IPBlock
from .dearpygui_async import DearPyGuiAsync
from .tools import Block, Tab, _hsv_to_rgb

CLASS_NAME_SEPARATOR = ':'

dpg_async = DearPyGuiAsync()

loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

# Dearpygui icons with DejaVuSans font
# ✗ ▲
# ● ○ ◆ ◇ ▲ △ ■ □
# ← → ↑ ↓ ↔ ⇒ ⇐ ⇑ ⇓ ➔

AdapterT = TypeVar("AdapterT", bound=BytesAdapter)

@overload
def adapter_block(adapter: IP) -> IPBlock: ...

@overload
def adapter_block(adapter: BytesAdapter) -> BytesAdapterBlock[Any]: ...

def adapter_block(adapter : BytesAdapter) -> BytesAdapterBlock[Any]:
    if isinstance(adapter, IP):
        return IPBlock(adapter)
    
    raise RuntimeError(f"Invalid adapter : {adapter}")

@overload
def protocol_block(protocol : Delimited) -> DelimitedBlock: ...
@overload
def protocol_block(protocol : Protocol[Any, Any]) -> ProtocolBlock[Any]: ...

def protocol_block(protocol : Protocol[Any, Any]) -> ProtocolBlock[Any]:
    if isinstance(protocol, Delimited):
        return DelimitedBlock(protocol)
    raise RuntimeError(f"Invalid protocol : {protocol}")


t = TypeVar("t", bound=Component[Any])

def default_ip() -> IP:
    return IP(address="", port=0, auto_open=False)

def default_serialport() -> SerialPort:
    return SerialPort(port="", baudrate=9600)

def default_delimited(adapter : BytesAdapter) -> Delimited:
    return Delimited(adapter, termination='\n')

class UIBase:
    """Main UI window"""
    def __init__(
            self,
            width : int = 1000,
            height : int = 600
        ) -> None:
        self._width = width
        self._height = height
        self._tab_bar : int | str = -1
        self.toplevel_component : Component[Any] | None = None
        self._tabs : list[Tuple[Tab, int | str]] = []
        self._build()

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
            height=self._height,
            min_width=self._width,
        )

        with dpg.window(
            width=self._width,
            height=self._height,
            no_resize=True,
            no_title_bar=True
        ) as self._window:

            with dpg.group(horizontal=True):
                # Left panel (configuration)
                with dpg.child_window(width=300):
                    dpg.add_text("Configuration")
                    with dpg.group(horizontal=True):
                        dpg.add_text("Status : ")
                        self._status_text = dpg.add_text("", wrap=300)
                        dpg.add_spacer()
                    with dpg.group(horizontal=True):
                        with dpg.theme() as red_button_theme:
                            with dpg.theme_component(dpg.mvButton):
                                dpg.add_theme_color(dpg.mvThemeCol_Button, _hsv_to_rgb(0, 0.6, 0.6))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, _hsv_to_rgb(0, 0.8, 0.8))
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, _hsv_to_rgb(0, 0.7, 0.7))

                        with dpg.theme() as green_button_theme:
                            with dpg.theme_component(dpg.mvButton):
                                dpg.add_theme_color(dpg.mvThemeCol_Button, _hsv_to_rgb(0.40, 0.6, 0.6))
                                dpg.add_theme_color(
                                    dpg.mvThemeCol_ButtonActive,
                                    _hsv_to_rgb(0.40, 0.8, 0.8)
                                )
                                dpg.add_theme_color(
                                    dpg.mvThemeCol_ButtonHovered,
                                    _hsv_to_rgb(0.40, 0.7, 0.7)
                                )

                        self._open_button = dpg.add_button(label="Open", callback=self.open, width=100)
                        dpg.bind_item_theme(dpg.last_item(), green_button_theme)
                        self._close_button = dpg.add_button(label="Close", callback=self.close, width=100)
                        dpg.bind_item_theme(dpg.last_item(), red_button_theme)

                    self._tab_bar = dpg.add_tab_bar()

                # Right panel (testing)
                with dpg.child_window(width=-1, height=-1) as self._testing_window:
                    ...


        self._status(False)

        dpg.set_primary_window(self._window, True)

        dpg.setup_dearpygui()

    def _add_adapter(self, block : BytesAdapterBlock) -> None:
        adapter_tab = dpg.add_tab(label=block.title, parent=self._tab_bar)
        self._tabs.append((block, adapter_tab))
        block.build_configuration_tab(adapter_tab)

    def load_adapter(self, adapter : BytesAdapter) -> None:
        block = adapter_block(adapter)
        self._add_adapter(block)
        adapter.register_event_callback(self._event_callback)
        block.build_testing_window(self._testing_window)

    def _add_protocol(self, protocol : Protocol[Any, Any]) -> None:
        _protocol_block = protocol_block(protocol)
        protocol_tab = dpg.add_tab(label=_protocol_block.title, parent=self._tab_bar)
        self._tabs.append((_protocol_block, protocol_tab))
        _protocol_block.build_configuration_tab(protocol_tab)

    def load_protocol(self, protocol : Protocol[Any, Any]) -> None:
        if not isinstance(protocol.adapter, BytesAdapter):
            raise RuntimeError("Non-bytes adapter are not yet supported")
        self._add_adapter(protocol.adapter)
        self._add_protocol(protocol)
        protocol.register_event_callback(self._event_callback)

    def load_driver(self, driver : Driver) -> None:
        ...

    def _add_driver(self, driver : Driver) -> None:
        ...

    def open(self) -> None:
        """Open the top-level component (driver, protocol or adapter)"""
        if self.toplevel_component is None:
            raise RuntimeError("Top-level component hasn't been set")
        self.toplevel_component.open()

        for block, _ in self._tabs:
            block.reset()

        try:
            if isinstance(self.toplevel_component, Adapter):
                self.toplevel_component.open()
            elif isinstance(self.toplevel_component, (Protocol, Driver)):
                self.toplevel_component.adapter.open()
            else:
                raise RuntimeError("Invalid top-level component")
        except AdapterOpenError as e:
            self._status(False, str(e))
        else:
            self._status(True)

    def close(self):
        if self.toplevel_component is None:
            raise RuntimeError("Top-level component hasn't been set")
        self.toplevel_component.close()

    def _event_callback(self, event : Event):
        ...

    def _status(self, opened : bool, text : str = "") -> None:
        if opened:
            dpg.disable_item(self._open_button)
            dpg.enable_item(self._close_button)
            dpg.set_value(self._status_text, "Opened")
            dpg.configure_item(self._status_text, color=(0,255,0))
        else:
            dpg.enable_item(self._open_button)
            dpg.disable_item(self._close_button)
            if text:
                dpg.set_value(self._status_text, f"Closed : {text}")
            else:
                dpg.set_value(self._status_text, "Closed")

            dpg.configure_item(self._status_text, color=(255,0,0))

class Command(StrEnum):
    """Syndesi ui CLI mode"""
    DRIVER_MODULE = 'module'
    DRIVER_PATH = 'path'
    IP = 'ip'
    SERIAL = 'serial'
    VISA = 'visa'
    MODBUS = 'modbus'
    DELIMITED = 'delimited'

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
    subparsers = parser.add_subparsers(dest='command')

    # Driver module
    driver_module_parser = subparsers.add_parser(Command.DRIVER_MODULE, help=COMMAND_HELP)
    driver_module_parser.add_argument('module', help="Module location")

    # Driver path
    driver_path_parser = subparsers.add_parser(Command.DRIVER_PATH)
    driver_path_parser.add_argument('path', help="Driver path")

    # IP
    ip_parser = subparsers.add_parser(Command.IP)
    # ip_parser.add_argument('address', help="IP address")
    # ip_parser.add_argument('port', help="IP port")

    # Serial
    serial_parser = subparsers.add_parser(Command.SERIAL)
    # serial_parser.add_argument("port", help="Serial port")
    # serial_parser.add_argument("")

    #parser.add_argument('argument', type=str, help="The mode argument, see the mode help")

    # Delimited
    delimited_parser = subparsers.add_parser(Command.DELIMITED)
    delimited_parser.add_argument('adapter', choices=[Command.IP, Command.SERIAL])

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
        ui.load_adapter(default_ip())
    if command == Command.DELIMITED:
        adapter = arguments.adapter
        if adapter == Command.IP:
            ui.load_protocol(default_delimited(default_ip()))
        elif adapter == Command.SERIAL:
            ui.load_protocol(default_delimited(default_serialport()))
    

    ui.start()

if __name__ == '__main__':
    main()
