# File : tester.py
# Author : Sébastien Deriaz
# License : GPL
"""
The tester is a UI based on dearpygui that allows the user to test functions of a given adapter, protocol or driver


"""
from enum import StrEnum

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

class KnownComponents(StrEnum):
    IP = 'ip'
    SERIAL = 'serial'
    VISA = 'visa'
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

    def _start(self):
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

def main(args : list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '--module', help="Module to open in the format package.module.driver:ClassName", default=None)
    parser.add_argument('-p', '--path', help="Path of the module to open in the format ./folder/driver.py:ClassName", default=None)

    args = parser.parse_args(args)
    module_arg = args.module
    path_arg = args.path

    if module_arg is not None and path_arg is not None:
        parser.error("Cannot specify both -m and -p")
        return
    elif module_arg is not None:
        module, class_name = module_arg.split(CLASS_NAME_SEPARATOR)
        m = importlib.import_module(module)
        c = getattr(m, class_name)
    elif path_arg is not None:
        path, class_name = path_arg.split(CLASS_NAME_SEPARATOR)
        m = importlib.util.spec_from_file_location(path)
        c = getattr(m, class_name)
    else:
        parser.error("Please specify a module with -m or -p")
        return


if __name__ == '__main__':
    main()