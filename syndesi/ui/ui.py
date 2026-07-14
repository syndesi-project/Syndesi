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
import time
import traceback
from typing import Any, Tuple, Type, TypeVar, overload

import dearpygui.dearpygui as dpg #type: ignore

from syndesi.adapters.adapter import Adapter
from syndesi.adapters.adapterworker import AdapterBufferEvent, AdapterClosedEvent, AdapterEvent, AdapterFragmentEvent, AdapterOpenedEvent, AdapterReadEvent, AdapterWriteEvent
from syndesi.adapters.bytesadapter import BytesAdapter
from syndesi.adapters.ip import IP
from syndesi.adapters.serialport import SerialPort
from syndesi.component import Component, Event
from syndesi.drivers.driver import Driver
from syndesi.protocols.delimited import Delimited
from syndesi.protocols.protocol import Protocol, ProtocolEvent
from syndesi.tools.errors import AdapterOpenError
from syndesi.ui.protocol import DelimitedBlock, ProtocolBlock

from .adapter import BytesAdapterBlock, IPBlock
from .dearpygui_async import DearPyGuiAsync
from .tools import Block, Tab, TestingChildWindow, TestingEntryType, _hsv_to_rgb

CLASS_NAME_SEPARATOR = ':'

dpg_async = DearPyGuiAsync()

loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

# Dearpygui icons with DejaVuSans font
# ✗ ▲
# ● ○ ◆ ◇ ▲ △ ■ □
# ← → ↑ ↓ ↔ ⇒ ⇐ ⇑ ⇓ ➔

AdapterT = TypeVar("AdapterT", bound=BytesAdapter)

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
        self.toplevel_block : Block | None = None
        self._tabs : list[Tuple[Tab, int | str]] = []
        self._event_queue : asyncio.Queue[AdapterEvent] = asyncio.Queue()
        self._start_timestamp = time.time()
        self._testing_bottom_group : int | str = -1
        self._build()
        asyncio.ensure_future(self.loop())

    def start(self) -> None:
        """Start the UI"""
        with dpg.font_registry():
            with importlib.resources.path("syndesi.fonts", "DejaVuSans.ttf") as f:
                with dpg.font(str(f), 16) as font:
                    dpg.bind_font(font)

        dpg.show_viewport()

        dpg_async.run()
        dpg.destroy_context()

    @overload
    def adapter_block(self, adapter: IP) -> IPBlock: ...

    @overload
    def adapter_block(self, adapter: BytesAdapter) -> BytesAdapterBlock[Any]: ...

    def adapter_block(self, adapter : BytesAdapter) -> BytesAdapterBlock[Any]:
        if isinstance(adapter, IP):
            return IPBlock(adapter, self._event_callback)
        
        raise RuntimeError(f"Invalid adapter : {adapter}")

    @overload
    def protocol_block(self, protocol : Delimited) -> DelimitedBlock: ...
    @overload
    def protocol_block(self, protocol : Protocol[Any, Any]) -> ProtocolBlock[Any]: ...

    def protocol_block(self, protocol : Protocol[Any, Any]) -> ProtocolBlock[Any]:
        if isinstance(protocol, Delimited):
            return DelimitedBlock(protocol)
        raise RuntimeError(f"Invalid protocol : {protocol}")

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
                    self._testing_child_window = TestingChildWindow()

                    with dpg.group(horizontal=False, parent=self._testing_window) as self._testing_top_group:
                        dpg.add_text("Testing")
                        dpg.add_checkbox(label="Show events", callback=self._show_events_callback, default_value=False)
                    self._testing_child_window.build(parent=self._testing_window)

                with dpg.item_handler_registry() as self._testing_window_resize_handler:
                    dpg.add_item_resize_handler(callback=self._testing_window_resize)
                    dpg.bind_item_handler_registry(self._testing_window, self._testing_window_resize_handler)

                

        self._testing_window_resize()

        self._status(False)

        dpg.set_primary_window(self._window, True)

        dpg.setup_dearpygui()

    def _testing_window_resize(self):
        if dpg.is_viewport_ok():
            dpg.render_dearpygui_frame()
        total_h = dpg.get_item_rect_size(self._testing_window)[1]
        a_h = dpg.get_item_rect_size(self._testing_top_group)[1]
        if self._testing_bottom_group != -1:
            c_h = dpg.get_item_rect_size(self._testing_bottom_group)[1]
        else:
            c_h = 0

        padding = 20

        b_h = max(total_h - a_h - c_h - 2*padding - 10, 50)
        self._testing_child_window.resize_height(b_h)

    def _show_events_callback(self):
        ...

    def _add_adapter(self, block : BytesAdapterBlock) -> None:
        adapter_tab = dpg.add_tab(label=block.title, parent=self._tab_bar)
        self._tabs.append((block, adapter_tab))
        block.build_configuration_tab(adapter_tab)

    def load_adapter(self, adapter : BytesAdapter) -> None:
        block = self.adapter_block(adapter)
        self._add_adapter(block)
        adapter.register_event_callback(self._event_callback)
        self._testing_bottom_group = block.build_testing_group(self._testing_window)
        self.toplevel_block = block
        dpg.bind_item_handler_registry(self._testing_bottom_group, self._testing_window_resize_handler)

    def _add_protocol(self, block : ProtocolBlock) -> None:
        protocol_tab = dpg.add_tab(label=block.title, parent=self._tab_bar)
        self._tabs.append((block, protocol_tab))
        block.build_configuration_tab(protocol_tab)

    def load_protocol(self, protocol : Protocol[Any, Any]) -> None:
        if not isinstance(protocol.adapter, BytesAdapter):
            raise RuntimeError("Non-bytes adapter are not yet supported")
        block = self.protocol_block(protocol)
        self._add_adapter(protocol.adapter)
        self._add_protocol(protocol)
        protocol.register_event_callback(self._event_callback)
        self.toplevel_block = block
        self._testing_bottom_group = block.build_testing_group(self._testing_window)

    def load_driver(self, driver : Driver) -> None:
        ...

    def _add_driver(self, driver : Driver) -> None:
        ...

    def open(self) -> None:
        """Open the top-level component (driver, protocol or adapter)"""
        if self.toplevel_block is None:
            raise RuntimeError("Top-level component hasn't been set")
        self.toplevel_block.open()

        for block, _ in self._tabs:
            block.reset()
            #block.load_ui_values()

        try:
            if isinstance(self.toplevel_block, BytesAdapterBlock):
                self.toplevel_block.open()
            elif isinstance(self.toplevel_block, ProtocolBlock):
                self.toplevel_block.adapter.open()
            else:
                raise RuntimeError("Invalid top-level component")
        except AdapterOpenError as e:
            self._status(False, str(e))
        else:
            self._status(True)

    def close(self):
        if self.toplevel_block is None:
            raise RuntimeError("Top-level component hasn't been set")
        self.toplevel_block.close()

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
    
    def _event_callback(self, event : AdapterEvent | ProtocolEvent) -> None:
        print(f'Event : {event}')
        loop.call_soon_threadsafe(self._event_queue.put_nowait, event)

    async def loop(self) -> None:
        """
        Event display loop
        """
        try:
            while True:
                event = await self._event_queue.get()
                #delta = event.timestamp - self._start_timestamp





                color = (255, 255, 255)
                text : str | None = None
                if isinstance(event, AdapterClosedEvent):
                    self._testing_child_window.add(TestingEntryType.CLOSE)
                elif isinstance(event, AdapterOpenedEvent):
                    self._testing_child_window.add(TestingEntryType.OPEN)
                elif isinstance(event, AdapterReadEvent):
                    self._testing_child_window.add(TestingEntryType.READ, f"{event.frame.data!r}")
                elif isinstance(event, AdapterFragmentEvent):# and \
                    #dpg.get_value(self._show_fragments_checkbox):
                    first_indicator = "*" if event.first else ""
                    self._testing_child_window.add(TestingEntryType.FRAGMENT, f"{event.fragment} ({first_indicator}frag)")
                elif isinstance(event, AdapterWriteEvent):
                    self._testing_child_window.add(TestingEntryType.WRITE, f"{event.frame.data!r}")
                # elif isinstance(event, AdapterBufferEvent):
                #     if self._adapter is not None:
                #         if len(event.added_frame_ids) > 0:
                #             for frame in self._adapter.frame_buffer:
                #                 if frame.id in event.added_frame_ids:
                #                     self._buffer_items[frame.id] = dpg.add_text(
                #                         str(frame.data),
                #                         parent=self._buffer_group
                #                     )

                #         for removed_frame_id in event.removed_frame_ids:
                #             tag = self._buffer_items.pop(removed_frame_id, None)
                #             if tag is not None:
                #                 dpg.delete_item(tag)
                else:
                    self._testing_child_window.add(TestingEntryType.UNKNOWN)

                # if text is not None:
                #     event_tag = dpg.add_group(horizontal=True, parent=self._event_group)
                #     dpg.add_text(f"{delta:+8.3f} ", color=(127, 127, 127), parent=event_tag)
                #     dpg.add_text(text, color=color, parent=event_tag)
                #     self._events.append(event_tag)

        except Exception:
            print(f'Exception in loop : {traceback.format_exc()}')

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
