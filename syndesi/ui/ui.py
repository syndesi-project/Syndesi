# File : tester.py
# Author : Sébastien Deriaz
# License : GPL
"""
The tester is a UI based on dearpygui that allows the user to test functions of a given adapter, protocol or driver


"""
from abc import ABC, abstractmethod
from enum import StrEnum
import argparse
import importlib
from typing import Callable

from syndesi.adapters.adapterworker import AdapterClosedEvent, AdapterEvent
from syndesi.adapters.ip import IP, IPDescriptor
from syndesi.adapters.serialport import SerialPort
from syndesi.adapters.stop_conditions import StopCondition, StopConditionType
from syndesi.adapters.visa import Visa
from syndesi.protocols.delimited import Delimited
from syndesi.protocols.modbus import Modbus
from syndesi.ui.tools import get_method_arguments

from ..adapters.adapter import Adapter, find_adapter_data_type

from ..adapters.genericadapter import GenericAdapter
from ..protocols.protocol import Protocol
from ..drivers.driver import Driver

class GenericAdapter(StrEnum):
    IP = 'ip'
    SERIAL = 'serial'
    VISA = 'visa'

class Protocol(StrEnum):
    MODBUS = 'modbus'
    DELIMTIED = 'delimited'

CLASS_NAME_SEPARATOR = ':'

def _check_dpg():
    try:
        import dearpygui.dearpygui
    except ImportError:
        raise RuntimeError("Missing dearpygui, please install with 'pip install dearpygui'")

class Block(ABC):
    @abstractmethod
    def build(self, parent : int) -> None:
        ...

class AdapterBlock(Block):
    on_close : Callable[[], None] | None = None
    on_open : Callable[[], None] | None = None

    def __init__(self) -> None:
        self._status_text : int | str = 0

    @abstractmethod
    def build(self, parent : int) -> None:
        with dpg.group(horizontal=True, parent=parent):
            dpg.add_text("Status : ")
            self._status_text = dpg.add_text("")
            self.close()

    def close(self):
        import dearpygui.dearpygui as dpg
        dpg.set_value(self._status_text, "Closed")
        dpg.configure_item(self._status_text, color=(255,0,0))

    def open(self):
        import dearpygui.dearpygui as dpg
        dpg.set_value(self._status_text, "Opened")
        dpg.configure_item(self._status_text, color=(0,255,0))

    @abstractmethod
    def _open_adapter(self):
        ...

    @abstractmethod
    def _close_adapter(self):
        ...

    def _on_adapter_event(self, event : AdapterEvent):
        if isinstance(event, AdapterClosedEvent):
            self._close_adapter()

class IPBlock(AdapterBlock):
    import dearpygui.dearpygui as dpg
    def __init__(self) -> None:
        super().__init__()
        self._adapter : IP | None = None
        self._stop_conditions_rows : list[list[int]] = []
        self._adapter_stop_conditions : list[StopCondition] = []

    def _clear_stop_conditions_table(self):
        for tags in self._stop_conditions_rows:
            for tag in tags:
                dpg.delete_item(tag)

    #def _add_stop_condition(self, index : int)

    def _stop_condition_combo_callback(self, sender, app_data : str, user_data : int):
        # app_data : New combo balue
        # user_data : Row index of the combo
        _type = StopConditionType(app_data.lower())
        if self._adapter_stop_conditions[user_data].type() != _type:
            # The stop-condition has changed
            self._adapter_stop_conditions = 

    def _update_stop_conditions_table(self):
        self._clear_stop_conditions_table()
        if self._adapter is not None:
            self._adapter_stop_conditions = self._adapter.stop_conditions
            for i, stop_condition in enumerate(self._adapter_stop_conditions):
                with dpg.table_row() as row:
                    combo = dpg.add_combo(
                        items=[x.value.upper() for x in StopConditionType],
                        callback=self._stop_condition_combo_callback,
                        user_data=i
                        )
                    _type = stop_condition.type()
                    if _type == StopConditionType.

                self._stop_conditions_rows.append(
                    [row, combo]
                )
        else:
            self._adapter_stop_conditions = []


    def build(self, parent : int):
        super().build(parent)
        import dearpygui.dearpygui as dpg
        with dpg.collapsing_header(label="IP Adapter", parent=parent, default_open=True):
            self._address_input = dpg.add_input_text(width=200, label="Address")
            self._port_input = dpg.add_input_text(width=200, label="Port")
            self._transport_input = dpg.add_combo(
                label="Transport",
                items=[x.value for x in IPDescriptor.Transport],
                default_value=IPDescriptor.Transport.TCP.value
            )
            timeout = IP.default_timeout()
            self._timeout_input = dpg.add_input_float(label="Timeout", default_value=timeout if timeout is not None else -1)

            with dpg.group(horizontal=True):
                dpg.add_button(label="Open", callback=self._open_adapter)
                dpg.add_button(label="Close", callback=self._close_adapter)
            
            with dpg.collapsing_header(label="Stop-conditions", default_open=False):
                with dpg.table() as self._stop_conditions_table:
                    dpg.add_table_column() # Type
                    dpg.add_table_column() # Arguments

                dpg.add_button(label="Add")
        self._update_stop_conditions_table()

    def _close_adapter(self):
        if self._adapter is not None:
            self._adapter.close()
            self._adapter = None
            if self.on_close is not None:
                self.on_close()
            self.close()
    
    def _open_adapter(self):
        import dearpygui.dearpygui as dpg
        address = dpg.get_value(self._address_input)
        port = int(dpg.get_value(self._port_input))
        transport = IPDescriptor.Transport(dpg.get_value(self._transport_input))
        timeout = float(dpg.get_value(self._timeout_input))
        self._adapter = IP(
            address=address,
            port=port,
            transport=transport,
            timeout=timeout if timeout >= 0 else None,
            auto_open=False,
        )
        self.open()
        if self.on_open is not None:
            self.on_open()

class UIBase:
    def __init__(
            self,
            width : int = 400,
            height : int = 600
        ) -> None:
        self._width = width
        self._height = height
        self._build()

    def start(self):
        import dearpygui.dearpygui as dpg
        dpg.show_viewport()
        dpg.start_dearpygui()
        dpg.destroy_context()

    
    def _build(self):
        import dearpygui.dearpygui as dpg
        dpg.create_context()
        dpg.create_viewport(
            title="Syndesi UI",
            width=self._width,
            height=self._height
        )
        
        self._window = dpg.add_window(
            width=self._width,
            height=self._height,
            no_title_bar=True
        )

        dpg.set_item_pos(self._window, [0,0])

        dpg.setup_dearpygui()

    def add_block(self, block : Block):
        block.build(parent=self._window)

# class UIAdapter:
#     def __init__(self, adapter : type[GenericAdapter]) -> None:
#         adapter_type = find_adapter_data_type(adapter)

# class UIProtocol:
#     def __init__(self, protocol : type[Protocol]) -> None:
#         protocol_input = 

# class UIDriver:
#     def __init__(self, driver : type[Driver]) -> None:
#         pass

class Mode(StrEnum):
    """Syndesi ui CLI mode"""
    DRIVER_MODULE = 'module'
    DRIVER_PATH = 'path'
    ADAPTER = 'adapter'
    PROTOCOL = 'protocol'

COMMAND_HELP = """The type of UI to open. Choose between : 

- 'module' : Open a driver with dot location like package.module.driver:DriverClass
- 'path' : Open a driver with a path to the file like ./folder/driver.py:DriverClass
- 'adapter' : Open an adapter (ip, serial, visa)
- 'protocol' : Open a protocol (delimited, modbus)
"""

import dearpygui.dearpygui as dpg

def main(args : list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=list(Mode), type=str)
    parser.add_argument('argument', type=str, help="The mode argument, see the mode help")

    args = parser.parse_args(args=args)

    mode = Mode(args.mode)
    argument = args.argument

    ui = UIBase()
    if mode == Mode.DRIVER_MODULE:
        module, class_name = argument.split(CLASS_NAME_SEPARATOR)
        m = importlib.import_module(module)
        c = getattr(m, class_name)
        ui = UIDriver(c)
    elif mode == Mode.DRIVER_PATH:
        path, class_name = argument.split(CLASS_NAME_SEPARATOR)
        m = importlib.util.spec_from_file_location(path)
        c = getattr(m, class_name)
        ui = UIDriver(c)
    elif mode == Mode.ADAPTER:
TODO : create an Adapter UI that provides stop-conditions selection
        adapter_name = GenericAdapter(argument)
        if adapter_name == GenericAdapter.IP:
            ui.add_block(IPBlock())
        elif adapter_name == GenericAdapter.SERIAL:
            ...
        elif adapter_name == GenericAdapter.VISA:
            ...
    elif mode == Mode.PROTOCOL:
        protocol_name = Protocol(argument)
        if protocol_name == Protocol.DELIMTIED:
            protocol = Delimited
        elif protocol_name == Protocol.MODBUS:
            protocol = Modbus
        ui = UIProtocol(protocol)
    
    ui.start()

if __name__ == '__main__':
    main()