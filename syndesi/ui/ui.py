# File : ui.py
# Author : Sébastien Deriaz
# License : GPL
"""
Syndesi UI
"""

import argparse
import asyncio
from dataclasses import dataclass
import importlib
import importlib.resources
from enum import IntEnum, StrEnum
import time
import traceback
from typing import Any, List, Tuple, Type, TypeVar, overload

import dearpygui.dearpygui as dpg #type: ignore

from syndesi.adapters.adapter import Adapter
from syndesi.adapters.adapterworker import (
    AdapterBufferEvent,
    AdapterClosedEvent,
    AdapterEvent,
    AdapterFragmentEvent,
    AdapterOpenedEvent,
    AdapterFrameEvent,
    AdapterReadEvent,
    AdapterWriteEvent,
    AdapterTimeoutUpdatedEvent,
    AdapterStopConditionsUpdatedEvent
)
from syndesi.adapters.bytesadapter import BytesAdapter
from syndesi.adapters.ip import IP
from syndesi.adapters.serialport import SerialPort
from syndesi.adapters.stop_conditions import StopConditionType
from syndesi.component import Component, SyndesiEvent
from syndesi.drivers.driver import Driver
from syndesi.protocols.delimited import Delimited
from syndesi.protocols.protocol import Protocol, ProtocolEvent
from syndesi.tools.errors import AdapterOpenError
from syndesi.ui.protocol import DelimitedBlock, ProtocolBlock

from .adapter import BytesAdapterBlock, IPBlock
from .dearpygui_async import DearPyGuiAsync
from .tools import ComponentBlock, ComponentBlock, _hsv_to_rgb

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

class TestingEntryType(IntEnum):
    UNKNOWN_EVENT = 0
    WRITE_EVENT = 1
    FRAME_EVENT = 2
    READ_EVENT = 3
    OPEN_EVENT = 4
    CLOSE_EVENT = 5
    FRAGMENT_EVENT = 6
    FIRST_FRAGMENT_EVENT = 7
    TOPLEVEL_READ = 8
    TOPLEVEL_WRITE = 9

    def is_adapter_event(self):
        return self in [
            TestingEntryType.FRAME_EVENT,
            TestingEntryType.FRAGMENT_EVENT,
            TestingEntryType.FIRST_FRAGMENT_EVENT,
            ]

ENTRY_PREFIX = {
    TestingEntryType.WRITE_EVENT : "→ write",
    TestingEntryType.FRAME_EVENT : "↓ frame",
    TestingEntryType.READ_EVENT : "←  read",
    TestingEntryType.TOPLEVEL_READ : "←  read",
    TestingEntryType.TOPLEVEL_WRITE : "→ write",
    TestingEntryType.OPEN_EVENT : "● opened",
    TestingEntryType.CLOSE_EVENT : "● closed",
    TestingEntryType.FRAGMENT_EVENT : "↓ frag", 
    TestingEntryType.FIRST_FRAGMENT_EVENT : "↓ frag*", 
    TestingEntryType.UNKNOWN_EVENT : "Invalid event",
}

ENTRY_COLOR = {
    TestingEntryType.WRITE_EVENT : (127, 127, 127),
    TestingEntryType.TOPLEVEL_WRITE : (212, 235, 197),
    TestingEntryType.FRAME_EVENT : (127, 127, 127),
    TestingEntryType.READ_EVENT : (127, 127, 127),
    TestingEntryType.TOPLEVEL_READ : (197, 213, 235),
    TestingEntryType.OPEN_EVENT : (30, 199, 38),
    TestingEntryType.CLOSE_EVENT : (207, 19, 19),
    TestingEntryType.FRAGMENT_EVENT : (127, 127, 127),
    TestingEntryType.FIRST_FRAGMENT_EVENT : (127, 127, 127),
    TestingEntryType.UNKNOWN_EVENT : (255, 0, 0),

}

@dataclass
class TestingEntry:
    entry_type : TestingEntryType
    group_tag : int | str

class UIBase:
    """Main UI window"""
    def __init__(
            self,
            #show_protocol_events_button : bool,
            #show_driver_events_button : bool,
            width : int = 1000,
            height : int = 600
        ) -> None:
        self._width = width
        self._height = height
        self._tab_bar : int | str = -1
        self.toplevel_component : ComponentBlock | None = None
        self._tabs : list[Tuple[ComponentBlock, int | str]] = []
        self._entry_queue : asyncio.Queue[TestingEntry] = asyncio.Queue()
        #self._event_queue : asyncio.Queue[AdapterEvent] = asyncio.Queue()
        self._start_timestamp = time.time()
        self._testing_bottom_group : int | str = -1
        self._entries : List[TestingEntry] = []
        self._testing_subwindow : int | str = -1
        self._show_adapter_events = False
        # self._show_protocol_events = False
        # self._show_driver_events = False
        # self._show_protocol_events_button = show_protocol_events_button
        # self._show_driver_events_button = show_driver_events_button
    
        
        self._build()
        #asyncio.ensure_future(self.loop())

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
    def adapter_block(self, adapter: IP, is_top_level : bool) -> IPBlock: ...

    @overload
    def adapter_block(self, adapter: BytesAdapter, is_top_level : bool) -> BytesAdapterBlock[Any]: ...

#    @overload
    def adapter_block(self, adapter : BytesAdapter, is_top_level : bool) -> BytesAdapterBlock[Any]:
        if isinstance(adapter, IP):
            return IPBlock(
                adapter,
                self._write_callback,
                self._read_callback,
                self._event_callback,
                is_top_level
            )
        
        raise RuntimeError(f"Invalid adapter : {adapter}")

    @overload
    def protocol_block(self, protocol : Delimited, is_top_level : bool) -> DelimitedBlock: ...
    @overload
    def protocol_block(self, protocol : Protocol[Any, Any], is_top_level : bool) -> ProtocolBlock[Any]: ...

    def protocol_block(self, protocol : Protocol[Any, Any], is_top_level : bool) -> ProtocolBlock[Any]:
        if isinstance(protocol, Delimited):
            return DelimitedBlock(protocol, self._write_callback, self._read_callback, is_top_level)
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
                        self._status_text = dpg.add_text("", wrap=200)
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

                    with dpg.group(horizontal=False, parent=self._testing_window) as self._testing_top_group:
                        dpg.add_text("Testing")

                        dpg.add_checkbox(label="Show adapter events", callback=self._show_adapter_events_callback, default_value=self._show_adapter_events)
                        # if self._show_protocol_events_button:
                        #     dpg.add_checkbox(label="Show protocol events", callback=self._show_protocol_events_callback, default_value=self._show_protocol_events)
                        # if self._show_driver_events_button:
                        #     dpg.add_checkbox(label="Show driver events", callback=self._show_driver_events_callback, default_value=self._show_adapter_events)
                
                    with dpg.child_window(parent=self._testing_window) as self._testing_subwindow:
                        with dpg.theme() as compact_theme:
                            with dpg.theme_component(dpg.mvAll):
                                dpg.add_theme_style(dpg.mvStyleVar_CellPadding, 4, 0, category=dpg.mvThemeCat_Core)

                        with dpg.table(policy=dpg.mvTable_SizingFixedFit) as self._testing_table:
                            dpg.add_table_column(label="Timestamp")
                            dpg.add_table_column(label="Event")
                            dpg.add_table_column(label="Data")

                        dpg.bind_item_theme(self._testing_table, compact_theme)

                with dpg.item_handler_registry() as self._testing_window_resize_handler:
                    dpg.add_item_resize_handler(callback=self._testing_window_resize)
                    dpg.bind_item_handler_registry(self._testing_window, self._testing_window_resize_handler)

                

        self._testing_window_resize()

        self._status(False)

        dpg.set_primary_window(self._window, True)

        dpg.setup_dearpygui()

    def _add_testing_entry(self, entry_type : TestingEntryType, time_delta : float, text : str = ""):
        with dpg.table_row(parent=self._testing_table) as row_tag:
            dpg.add_text(f"{time_delta:+8.3f}", color=ENTRY_COLOR[entry_type])
            dpg.add_text(ENTRY_PREFIX[entry_type], color=ENTRY_COLOR[entry_type])
            dpg.add_text(text, color=ENTRY_COLOR[entry_type])

        self._entries.append(TestingEntry(
            entry_type=entry_type,
            group_tag=row_tag
        ))
        if not self._show_adapter_events and entry_type.is_adapter_event():
            dpg.hide_item(row_tag)

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
        dpg.configure_item(self._testing_subwindow, height=b_h)

    def _show_adapter_events_callback(self, sender : int | str, value : bool):
        self._show_adapter_events = value
        for entry in self._entries:
            if entry.entry_type.is_adapter_event():
                if self._show_adapter_events:
                    dpg.show_item(entry.group_tag)
                else:
                    dpg.hide_item(entry.group_tag)


    def _add_adapter(self, block : BytesAdapterBlock) -> None:
        adapter_tab = dpg.add_tab(label=block.title, parent=self._tab_bar)
        self._tabs.append((block, adapter_tab))
        block.build_configuration_tab(adapter_tab)

    def load_adapter(self, adapter : BytesAdapter) -> None:
        block = self.adapter_block(adapter, True)
        self._add_adapter(block)
        self._testing_bottom_group = block.build_testing_group(self._testing_window)
        self.toplevel_component = block
        dpg.bind_item_handler_registry(self._testing_bottom_group, self._testing_window_resize_handler)

    def _add_protocol(self, block : ProtocolBlock) -> None:
        protocol_tab = dpg.add_tab(label=block.title, parent=self._tab_bar)
        self._tabs.append((block, protocol_tab))
        block.build_configuration_tab(protocol_tab)

    def load_protocol(self, protocol : Protocol[Any, Any]) -> None:
        if not isinstance(protocol.adapter, BytesAdapter):
            raise RuntimeError("Non-bytes adapter are not yet supported")
        block = self.protocol_block(protocol, True)
        self._add_adapter(self.adapter_block(protocol.adapter, False))
        self._add_protocol(block)
        self.toplevel_component = block
        self._testing_bottom_group = block.build_testing_group(self._testing_window)

    def load_driver(self, driver : Driver) -> None:
        ...

    def _add_driver(self, driver : Driver) -> None:
        ...

    def open(self) -> None:
        """Open the top-level component (driver, protocol or adapter)"""
        if self.toplevel_component is None:
            raise RuntimeError("Top-level component hasn't been set")

        for block, _ in self._tabs:
            block.sync_block_to_component()

        try:
            self.toplevel_component.open()
        except AdapterOpenError as e:
            self._status(False, str(e))

        # No need to update status to True here, it will be done by the event

    def close(self):
        if self.toplevel_component is None:
            raise RuntimeError("Top-level component hasn't been set")
        self.toplevel_component.close()
        self._status(False)

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
        delta = event.timestamp - self._start_timestamp
        # Only adapter events are received and displayed
        # Use adapter close and open events to show open and close
        if isinstance(event, AdapterClosedEvent):
            #self._add_testing_entry(TestingEntryType.CLOSE_EVENT, delta)
            loop.call_soon_threadsafe(self._add_testing_entry, TestingEntryType.CLOSE_EVENT, delta)
            self._status(False)
        elif isinstance(event, AdapterOpenedEvent):
            #self._add_testing_entry(TestingEntryType.OPEN_EVENT, delta)
            loop.call_soon_threadsafe(self._add_testing_entry, TestingEntryType.OPEN_EVENT, delta)
            self._status(True)
        elif isinstance(event, AdapterFrameEvent):
            if event.frame.stop_condition is None:
                sc_data = "(error)"
            else:
                sc_data = str(event.frame.stop_condition)
            #self._add_testing_entry(TestingEntryType.FRAME_EVENT, delta, f"{event.frame.data!r} ({sc_data})")
            loop.call_soon_threadsafe(
                self._add_testing_entry,
                TestingEntryType.FRAME_EVENT,
                delta,
                f"{event.frame.data!r} ({sc_data})"
                )
        elif isinstance(event, AdapterFragmentEvent):
            # self._add_testing_entry(
            #     TestingEntryType.FIRST_FRAGMENT_EVENT if event.first else TestingEntryType.FRAGMENT_EVENT,
            #     delta, str(event.fragment.data)
            # )
            loop.call_soon_threadsafe(
                self._add_testing_entry,
                TestingEntryType.FIRST_FRAGMENT_EVENT if event.first else TestingEntryType.FRAGMENT_EVENT,
                delta,
                str(event.fragment.data))
        elif isinstance(event, AdapterReadEvent):
            loop.call_soon_threadsafe(self._add_testing_entry, TestingEntryType.READ_EVENT, delta, f"{event.frame.data}" + " (buffer)" if event.from_buffer else "")
        elif isinstance(event, AdapterWriteEvent):
            loop.call_soon_threadsafe(self._add_testing_entry, TestingEntryType.WRITE_EVENT, delta, f"{event.frame.data!r}")

        # elif isinstance(event, (AdapterReadEvent, ProtocolReadEvent)):
        #     message = 
        #     #if is_top_level:
        #     #    loop.call_soon_threadsafe(self._add_testing_entry, TestingEntryType.TOPLEVEL_READ, delta, message)
        #     #else:

        #     message = 
        #     #if is_top_level:
        #     #    loop.call_soon_threadsafe(self._add_testing_entry, TestingEntryType.TOPLEVEL_WRITE, delta, message)
        #     #else:
        elif isinstance(event, 
                        (AdapterBufferEvent,
                            AdapterTimeoutUpdatedEvent,
                            AdapterStopConditionsUpdatedEvent)
                        ):
            ...
        else:
            loop.call_soon_threadsafe(self._add_testing_entry, TestingEntryType.UNKNOWN_EVENT, delta)


        #loop.call_soon_threadsafe(self._event_queue.put_nowait, (event, is_top_level))

    def _write_callback(self, data : str):
        t = time.time()
        delta = t - self._start_timestamp
        loop.call_soon_threadsafe(self._add_testing_entry, TestingEntryType.TOPLEVEL_WRITE, delta, data)

    def _read_callback(self, data : str):
        t = time.time()
        delta = t - self._start_timestamp
        loop.call_soon_threadsafe(self._add_testing_entry, TestingEntryType.TOPLEVEL_READ, delta, data)

    async def loop(self) -> None:
        """
        Event display loop
        """
#        try:
#            while True:
                # event, is_top_level = await self._event_queue.get()
                # print(f'Event {event} top_level={is_top_level}')
                # delta = event.timestamp - self._start_timestamp
                # # Only adapter events are received and displayed
                # # Use adapter close and open events to show open and close
                # if isinstance(event, AdapterClosedEvent):
                #     self._add_testing_entry(TestingEntryType.CLOSE_EVENT, delta)
                #     self._status(False)
                # elif isinstance(event, AdapterOpenedEvent):
                #     self._add_testing_entry(TestingEntryType.OPEN_EVENT, delta)
                #     self._status(True)
                # elif isinstance(event, AdapterFrameEvent):
                #     if event.frame.stop_condition is None:
                #         sc_data = "(error)"
                #     else:
                #         sc_data = str(event.frame.stop_condition)
                #     self._add_testing_entry(TestingEntryType.FRAME_EVENT, delta, f"{event.frame.data!r} ({sc_data})")
                # elif isinstance(event, AdapterFragmentEvent):
                #     self._add_testing_entry(
                #         TestingEntryType.FIRST_FRAGMENT_EVENT if event.first else TestingEntryType.FRAGMENT_EVENT,
                #         delta, str(event.fragment.data)
                #     )
                # elif isinstance(event, (AdapterReadEvent, ProtocolReadEvent)):
                #     message = f"{event.frame.data}" + " (buffer)" if event.from_buffer else ""
                #     if is_top_level:
                #         self._add_testing_entry(TestingEntryType.TOPLEVEL_READ, delta, message)
                #     else:
                #         self._add_testing_entry(TestingEntryType.READ_EVENT, delta, message)

                # elif isinstance(event, (AdapterWriteEvent, ProtocolWriteEvent)):
                #     message = f"{event.frame.data!r}"
                #     if is_top_level:
                #         self._add_testing_entry(TestingEntryType.TOPLEVEL_WRITE, delta, message)
                #     else:
                #         self._add_testing_entry(TestingEntryType.WRITE_EVENT, delta, message)
                # elif isinstance(event, 
                #                 (AdapterBufferEvent,
                #                  AdapterTimeoutUpdatedEvent,
                #                  AdapterStopConditionsUpdatedEvent)
                #                 ):
                #     ...
                # else:
                #     self._add_testing_entry(TestingEntryType.UNKNOWN_EVENT, delta)

        # except Exception:
        #     print(f'Exception in loop : {traceback.format_exc()}')

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

    # is_adapter = command in [Command.IP, Command.SERIAL, Command.VISA]
    # is_protocol = command in [Command.DELIMITED, Command.MODBUS]
    # is_driver = command in [Command.DRIVER_MODULE, Command.DRIVER_PATH]
    # if not is_adapter and not is_protocol and not is_driver:
    #     raise RuntimeError(f"Unclassified command : {command}")


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
