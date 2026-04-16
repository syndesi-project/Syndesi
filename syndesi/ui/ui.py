# File : tester.py
# Author : Sébastien Deriaz
# License : GPL
"""
The tester is a UI based on dearpygui that allows the user to test functions of a given adapter,
protocol or driver
"""

from abc import ABC, abstractmethod
import asyncio
from enum import StrEnum
import argparse
import importlib
import time
from typing import Any, Callable, Generic, TypeVar
import ast
from .dearpygui_async import DearPyGuiAsync

from syndesi.adapters.adapterworker import AdapterClosedEvent, AdapterEvent, AdapterFirstFragmentEvent, AdapterFrameEvent, AdapterOpenedEvent
from syndesi.adapters.ip import IP, IPDescriptor
from syndesi.adapters.serialport import SerialPort
from syndesi.adapters.stop_conditions import STOP_CONDITION_BY_TYPE, Continuation, FragmentSC, Length, StopCondition, StopConditionType, Termination, Total
from syndesi.adapters.visa import Visa
from syndesi.component import ReadScope
from syndesi.protocols.delimited import Delimited
from syndesi.protocols.modbus import Modbus
from syndesi.tools.errors import AdapterOpenError, AdapterReadError, AdapterTimeoutError, AdapterWriteError
from syndesi.ui.tools import get_method_arguments

from ..adapters.adapter import find_adapter_data_type
from ..adapters.bytesadapter import BytesAdapter

from ..drivers.driver import Driver

import dearpygui.dearpygui as dpg # type: ignore[import-untyped]


import importlib.resources
import dearpygui.dearpygui as dpg

CLASS_NAME_SEPARATOR = ':'

dpg_async = DearPyGuiAsync()

class Block(ABC):
    @abstractmethod
    def build(self, parent : int | str) -> None:
        ...

StopConditionT = TypeVar("StopConditionT", bound=StopCondition)

class StopConditionBlock(Generic[StopConditionT], Block):
    _stop_condition : StopConditionT
    items : list[int | str] = []
    tab : int | str = -1
    def __init__(self, stop_condition : StopConditionT) -> None:
        super().__init__()
        self._stop_condition = stop_condition

    def clear(self) -> None:
        """Delete all dpg items"""
        for item in self.items:
            dpg.delete_item(item)

    @abstractmethod
    def build(self, parent: int | str) -> None:
        ...

class TerminationBlock(StopConditionBlock[Termination]):
    """Termination stop-condition block"""
    def __init__(self, stop_condition: Termination) -> None:
        super().__init__(stop_condition)
        self._termination_input : int | str = -1
        self._error_text : int | str = -1
    def build(self, parent : int | str) -> None:
        with dpg.tab(label=str(self._stop_condition), parent=parent) as self.tab:
            with dpg.group(horizontal=True):
                dpg.add_text("b'")
                self._termination_input = dpg.add_input_text(
                    label="Termination",
                    callback=self._termination_callback,
                    default_value=repr(self._stop_condition.sequence)[2:-1]
                )
                dpg.add_text("'")
            self._error_text = dpg.add_text("", parent=parent, color=(255,0,0), show=False)

        self.items += [self._termination_input, self._error_text, self.tab]

    def _termination_callback(self, _ : int | str, app_data : str) -> None:
        try:
            sequence_bytes = ast.literal_eval(f"b{app_data!r}")
        except ValueError:
            dpg.set_value(self._error_text, "Could not parse sequence")
            dpg.show_item(self._error_text)
        else:
            dpg.hide_item(self._error_text)
            self._stop_condition = Termination(sequence_bytes)

class LengthBlock(StopConditionBlock[Length]):
    """
    Length stop-condition block
    """
    DEFAULT_LENGTH = 10
    def __init__(self, stop_condition : Length) -> None:
        length = self.DEFAULT_LENGTH if stop_condition is None else stop_condition.n
        self._stop_condition = Length(length)
        self._length_input : int | str = -1

    def build(self, parent : int | str) -> None:
        with dpg.tab(label=str(self._stop_condition), parent=parent) as self.tab:
            self._length_input = dpg.add_input_int(
                label="Length",
                callback=self._length_callback,
                default_value=self._stop_condition.n
            )

        self.items += [self._length_input, self.tab]

    def _length_callback(self, _ : int | str, app_data : int) -> None:
        self._stop_condition = Length(app_data)

class ContinuationBlock(StopConditionBlock[Continuation]):
    """Continuation stop-condition block"""
    DEFAULT_CONTINUATION = 0.2
    def __init__(self, stop_condition : Continuation) -> None:
        continuation = self.DEFAULT_CONTINUATION if stop_condition is None else stop_condition.continuation
        self._stop_condition  = Continuation(continuation)
    
    def build(self, parent : int | str) -> None:
        with dpg.tab(label=str(self._stop_condition), parent=parent) as self.tab:
            self._continuation_input = dpg.add_input_float(
                label="Continuation time [s]",
                min_value=0,
                min_clamped=True,
                width=100,
                default_value=self._stop_condition.continuation,
                callback=self._continuation_callback
            )

        self.items += [self._continuation_input, self.tab]
    
    def _continuation_callback(self, _ : int | str, app_data : float) -> None:
        self._stop_condition = Continuation(app_data)

class TotalBlock(StopConditionBlock[Total]):
    """Total stop-condition block"""
    DEFAULT_TOTAL = 0.2
    def __init__(self, stop_condition : Total) -> None:
        total = self.DEFAULT_TOTAL if stop_condition is None else stop_condition.total
        self._stop_condition = Total(total)
        self._total_input : int | str = -1
    
    def build(self, parent : int | str) -> None:
        with dpg.tab(label=str(self._stop_condition), parent=parent) as self.tab:
            self._total_input = dpg.add_input_float(
                label="Total time [s]",
                min_value=0,
                min_clamped=True,
                default_value=self._stop_condition.total,
                callback=self._total_callback
            )
        self.items += [self._total_input, self.tab]
    
    def _total_callback(self, _ : int | str, app_data : float) -> None:
        self._stop_condition = Total(app_data)

class FragmentBlock(StopConditionBlock[FragmentSC]):
    """Fragment stop-condition block"""
    def build(self, parent : int | str) -> None:
        with dpg.tab(label=str(self._stop_condition), parent=parent) as self.tab:
            ...
        self.items += [self.tab]

AdapterT = TypeVar("AdapterT", bound=BytesAdapter)


class BytesAdapterBlock(Generic[AdapterT], Block):
    """BytesAdapter UI block"""
    _adapter : AdapterT
    #on_close : Callable[[], None] | None = None
    #on_open : Callable[[], None] | None = None
    STOP_CONDITIONS_COMBO_ITEMS = [x.value.capitalize() for x in StopConditionType if x != StopConditionType.TIMEOUT]

    def __init__(self, title : str) -> None:
        self._status_text : int | str = 0
        self._stop_conditions_cache : list[StopConditionBlock[Any]] = []
        self._tab_bar : int | str = -1
        self._combo : int | str = -1
        self._timeout_input : int | str = -1
        self._title = title
        self._write_input : int | str = -1
        self._write_status : int | str = -1
        self._read_output : int | str = -1
        self._read_start : float = 0
        self._read_task_running = False
        self._header : int | str = -1
        self._event_window : int | str = -1
        self._events = []

        self._adapter.register_event_callback(self._on_adapter_event)

    @abstractmethod
    def _build_descriptor(self, parent : int | str) -> None:
        ...

    def build(self, parent : int | str) -> None:
        with dpg.collapsing_header(
            label=self._title,
            parent=parent,
            default_open=True
        ) as self._header:
            with dpg.group(horizontal=True):
                dpg.add_text("⏷●●↓🡇🡲➔ Status : ")
                self._status_text = dpg.add_text("")
                self.close()
            self._build_descriptor(self._header)
            timeout = self._adapter.default_timeout()
            self._timeout_input = dpg.add_input_float(
                label="Timeout",
                default_value=timeout if timeout is not None else -1,
                width=100
            )

            with dpg.group(horizontal=True):
                dpg.add_button(label="Open", callback=self.open)
                dpg.add_button(label="Close", callback=self.close)
            
            dpg.add_spacer(height=5)
            dpg.add_separator()
            dpg.add_spacer(height=5)
            dpg.add_text("Stop-conditions", color=(70, 142, 194))
            with dpg.group(horizontal=True):
                dpg.add_button(label="Add", callback=self._add_callback)
                self._combo = dpg.add_combo(
                    self.STOP_CONDITIONS_COMBO_ITEMS,
                    default_value="",
                    width=120
                )
                dpg.add_button(label="Remove", callback=self._remove_callback)
                dpg.add_button(label="Update", callback=self._cache_stop_conditions_to_adapter)
            with dpg.tab_bar(reorderable=True) as self._tab_bar:
                ...

            dpg.add_spacer(height=5)
            dpg.add_separator()
            dpg.add_spacer(height=5)

            with dpg.group(horizontal=True):
                with dpg.group(horizontal=False):
                    dpg.add_text("Write", color=(70, 142, 194))
                    dpg.add_button(label="Write", callback=self._write_callback, width=60)
                    with dpg.group(horizontal=True):        
                        dpg.add_text("b'")
                        self._write_input = dpg.add_input_text(width=200)
                        dpg.add_text("'")
                    self._write_status = dpg.add_text("")
                dpg.add_spacer(width=20)
                with dpg.group(horizontal=False):
                    dpg.add_text("Read", color=(70, 142, 194))
                    dpg.add_combo(label="Scope", items=[x for x in ReadScope], width=80, default_value=ReadScope.BUFFERED.value)
                    dpg.add_button(label="Read", callback=self._read_callback, width=60)
                    self._read_output = dpg.add_text("")

            with dpg.collapsing_header(label="Adapter events"):
                with dpg.child_window(height=100, width=400) as self._event_window:
                    ...

        self._adapter_to_cache_stop_conditions()

    async def _read_callback(self) -> None:
        self._read_start = time.time()
        asyncio.create_task(self._read_task())
        try:
            data = await self._adapter.aread()
        except AdapterTimeoutError as e:
            self._read_task_running = False
            dpg.set_value(self._read_output, f"Read timeout ({e.timeout})")
            dpg.configure_item(self._read_output, color=(237, 117, 31))
        except AdapterReadError as e:
            self._read_task_running = False
            dpg.set_value(self._read_output, str(e))
            dpg.configure_item(self._read_output, color=(255,0,0))
        else:
            self._read_task_running = False
            dpg.set_value(self._read_output, repr(data))
            dpg.configure_item(self._read_output, color=(86, 178, 245))


    async def _read_task(self) -> None:
        self._read_task_running = True
        dpg.configure_item(self._read_output, color=None)
            
        while self._read_task_running:
            dpg.set_value(self._read_output, f"{time.time() - self._read_start:.3f}s")
            await asyncio.sleep(1/60)

    def _write_callback(self) -> None:
        try:
            data : bytes = ast.literal_eval(f"b'{dpg.get_value(self._write_input)}'")
        except SyntaxError as e:
            dpg.set_value(self._write_status, str(e))
            return

        try:
            self._adapter.write(data)
        except AdapterWriteError as e:
            dpg.set_value(self._write_status, str(e))
        else:
            dpg.set_value(self._write_status, "")

    def _add_callback(self) -> None:
        stop_condition = dpg.get_value(self._combo).lower()
        try:
            _type = StopConditionType(stop_condition)
        except ValueError:
            ...
        else:
            self._add_default_stop_condition(_type)

    def _remove_callback(self) -> None:
        selected_tab = dpg.get_value(self._tab_bar)
        for block in self._stop_conditions_cache:
            if block.tab == selected_tab:
                self._stop_conditions_cache.remove(block)
                break
        
        self._cache_stop_conditions_to_adapter()

    def _status(self, opened : bool, text : str = "") -> None:
        if opened:
            dpg.set_value(self._status_text, "Opened")
            dpg.configure_item(self._status_text, color=(0,255,0))
        else:
            if text:
                dpg.set_value(self._status_text, f"Closed : {text}")
            else:
                dpg.set_value(self._status_text, "Closed")
            
            dpg.configure_item(self._status_text, color=(255,0,0))

    def open(self) -> None:
        """Open adapter"""
        if self._adapter is not None:
            try:
                self._adapter.open()
            except AdapterOpenError as e:
                self._status(False, str(e))
            else:
                self._status(True)

    def _add_default_stop_condition(self, _type : StopConditionType) -> None:
        stop_condition : StopCondition
        if _type == StopConditionType.CONTINUATION:
            stop_condition = Continuation(0.2)
        elif _type == StopConditionType.FRAGMENT:
            stop_condition = FragmentSC()
        elif _type == StopConditionType.LENGTH:
            stop_condition = Length(10)
        elif _type == StopConditionType.TERMINATION:
            stop_condition = Termination("\n")
        elif _type == StopConditionType.TOTAL:
            stop_condition = Total(5)
        else:
            raise RuntimeError("Invalid stop-condition type")

        self._add_stop_condition(stop_condition)

    def _add_stop_condition(self, stop_condition : StopCondition) -> StopConditionBlock[Any]:
        block : StopConditionBlock[Any]
        if isinstance(stop_condition, Termination):
            block = TerminationBlock(stop_condition)
        elif isinstance(stop_condition, Length):
            block = LengthBlock(stop_condition)
        elif isinstance(stop_condition, Continuation):
            block = ContinuationBlock(stop_condition)
        elif isinstance(stop_condition, Total):
            block = TotalBlock(stop_condition)
        elif isinstance(stop_condition, FragmentSC):
            block = FragmentBlock(stop_condition)
        else:
            raise RuntimeError("Invalid stop-condition type")

        block.build(self._tab_bar)

        self._stop_conditions_cache.append(block)

        return block

    def _clear_stop_conditions(self) -> None:
        for stop_condition_block in self._stop_conditions_cache:
            stop_condition_block.clear()
        self._stop_conditions_cache.clear()

    def _cache_stop_conditions_to_adapter(self) -> None:
        ...

    def _adapter_to_cache_stop_conditions(self) -> None:
        self._clear_stop_conditions()

        if self._adapter is not None:
            for stop_condition in self._adapter.stop_conditions:
                self._add_stop_condition(stop_condition)

    def close(self) -> None:
        """Close adapter"""
        self._adapter.close()
        

    def _on_adapter_event(self, event : AdapterEvent) -> None:
        event : int | str = -1
        print(f'Adapter event : {event}')
        if isinstance(event, AdapterClosedEvent):
            self._status(False)
            with dpg.group(parent=self._event_window) as event:
                dpg.add_text("● closed", color=(207, 19, 19))

        elif isinstance(event, AdapterOpenedEvent):
            with dpg.group(parent=self._event_window) as event:
                dpg.add_text("● open", color=(30, 199, 38))

        elif isinstance(event, AdapterFrameEvent):
            with dpg.group(parent=self._event_window) as event:
                dpg.add_text("← read")

        elif isinstance(event, AdapterFirstFragmentEvent):
            ...

        elif isinstance(event, AdapterFragmentEvent):
            with dpg.group(parent=self._event_window) as event:
                dpg.add_text("↓")

        self._events.append(event)

class IPBlock(BytesAdapterBlock[IP]):
    """IP adapter block"""
    def __init__(self) -> None:
        self._adapter = IP(address="", port=0, auto_open=False)
        super().__init__("IP Adapter")
        self._address_input : int | str = -1
        self._port_input : int | str = -1
        self._port_details : int | str = -1
        self._transport_input : int | str = -1
        
    def _build_descriptor(self, parent : int | str) -> None:
        dpg.add_text("Descriptor", color=(70, 142, 194), parent=parent)
        self._address_input = dpg.add_input_text(
            width=150,
            label="Address",
            default_value=self._adapter.descriptor.address,
            parent=parent
        )
        with dpg.group(horizontal=True):
            with dpg.group(horizontal=True, parent=parent):
                self._port_input = dpg.add_input_text(width=100, label="Port", default_value=str(self._adapter.descriptor.port))
                self._port_details = dpg.add_text("")
        self._transport_input = dpg.add_combo(
            parent=parent,
            label="Transport",
            items=[x.value for x in IPDescriptor.Transport],
            default_value=IPDescriptor.Transport.TCP.value,
            width=100
        )
    
    def open(self) -> None:
        address = dpg.get_value(self._address_input)
        try:
            port = int(dpg.get_value(self._port_input))
        except ValueError:
            dpg.set_value(self._port_details, "Invalid port")
            return
        else:
            dpg.set_value(self._port_details, "")
        transport = IPDescriptor.Transport(dpg.get_value(self._transport_input))
        timeout = float(dpg.get_value(self._timeout_input))
        self._adapter = IP(
            address=address,
            port=port,
            transport=transport,
            timeout=timeout if timeout >= 0 else None,
            auto_open=False
        )
        #self._adapter.register_event_callback(self._on_adapter_event)
        super().open()

        self._adapter_to_cache_stop_conditions()

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

    def start(self) -> None:
        with dpg.font_registry():            
            with importlib.resources.path("syndesi.fonts", "DejaVuSans.ttf") as f:
                with dpg.font(f, 16) as font:
                    dpg.bind_font(font)

        dpg.show_viewport()
        dpg_async.run() # run; replaces `dpg.start_dearpygui()`
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
        dpg.add_text("Statut → OK   Erreur ✗   Niveau ▲",parent=self.window)
        dpg.add_text("Points : ● ○ ◆ ◇ ▲ ■ ● Formes : ■ □ ▲ △",parent=self.window)
        dpg.add_text("Flèches : ← → ↑ ↓ ↔ ⇒ ⇐ ⇑ ⇓",parent=self.window)

        # Ouvre le font manager pour inspecter visuellement
        dpg.show_font_manager()

        dpg.set_primary_window(self.window, True)

        dpg.setup_dearpygui()

    def add_block(self, block : Block) -> None:
        """Add a display block to the window"""
        block.build(self.window)

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
    if command == Command.DRIVER_MODULE:
        module, class_name = argument.split(CLASS_NAME_SEPARATOR)
        m = importlib.import_module(module)
        c = getattr(m, class_name)
        ui = UIDriver(c)
    elif command == Command.DRIVER_PATH:
        path, class_name = argument.split(CLASS_NAME_SEPARATOR)
        m = importlib.util.spec_from_file_location(path)
        c = getattr(m, class_name)
        ui = UIDriver(c)
    elif command == Command.IP:
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