# File : tester.py
# Author : Sébastien Deriaz
# License : GPL
"""
The tester is a UI based on dearpygui that allows the user to test functions of a given adapter, protocol or driver


"""
from enum import StrEnum

from syndesi.adapters.ip import IP
from syndesi.adapters.serialport import SerialPort
from syndesi.adapters.visa import Visa
from syndesi.protocols.delimited import Delimited
from syndesi.protocols.modbus import Modbus

from ..adapters.adapterbase import find_adapter_data_type

from ..adapters.adapter import Adapter
from ..protocols.protocol import Protocol
from ..drivers.driver import Driver

import argparse

import importlib

try:
    import dearpygui.dearpygui as dpg
except ImportError:
    dpg = None

class Adapter(StrEnum):
    IP = 'ip'
    SERIAL = 'serial'
    VISA = 'visa'

class Protocol(StrEnum):
    MODBUS = 'modbus'
    DELIMTIED = 'delimited'
    
CLASS_NAME_SEPARATOR = ':'

class UIBase:
    def __init__(self) -> None:
        
        if dpg is None:
            raise RuntimeError(
                "Cannot run the Tester UI without dearpygui. Install with 'pip install dearpygui'"
            )
        self.dpg = dpg

    def start(self):
        self.dpg.start_dearpygui()
        self.dpg.destroy_context()

    
    def _build(self):
        self.dpg.create_context()
        
        with dpg.window(label="Syndesi UI"):
            dpg.add_text("test")

class UIAdapter:
    def __init__(self, adapter : Adapter) -> None:
        adapter_type = find_adapter_data_type(adapter)

class UIProtocol:
    def __init__(self, protocol : Protocol) -> None:
        pass

class UIDriver:
    def __init__(self, driver : Driver) -> None:
        pass

class Mode(StrEnum):
    MODULE = 'module'
    PATH = 'path'
    ADAPTER = 'adapter'
    PROTOCOL = 'protocol'

COMMAND_HELP = """The type of UI to open. Choose between : 

- 'module' : Open a driver with dot location like package.module.driver:DriverClass
- 'path' : Open a driver with a path to the file like ./folder/driver.py:DriverClass
- 'adapter' : Open an adapter (ip, serial, visa)
- 'protocol' : Open a protocol (delimited, modbus)
"""

def main(args : list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=list(Mode), type=str)
    parser.add_argument('argument', type=str, help="The mode argument, see the mode help")

    args = parser.parse_args(args)


    mode = Mode(args.command)
    argument = args.argument

    if mode == Mode.MODULE:
        module, class_name = argument.split(CLASS_NAME_SEPARATOR)
        m = importlib.import_module(module)
        c = getattr(m, class_name)
        ui = UIDriver(c)
    elif mode == Mode.PATH:
        path, class_name = argument.split(CLASS_NAME_SEPARATOR)
        m = importlib.util.spec_from_file_location(path)
        c = getattr(m, class_name)
        ui = UIDriver(c)
    elif mode == Mode.ADAPTER:
        adapter_name = Adapter(argument)
        if adapter_name == Adapter.IP:
            adapter = IP
        elif adapter_name == Adapter.SERIAL:
            adapter = SerialPort
        elif adapter_name == Adapter.VISA:
            adapter = Visa
        ui = UIAdapter(adapter)
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