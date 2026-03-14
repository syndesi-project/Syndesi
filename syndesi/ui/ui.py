# File : tester.py
# Author : Sébastien Deriaz
# License : GPL
"""
The tester is a UI based on dearpygui that allows the user to test functions of a given adapter, protocol or driver


"""
from enum import StrEnum
from ..component import Component

import inspect
import argparse

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
    

class UI:
    def __init__(self, component : Component) -> None:
        
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

    


def main(args : list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument('component', help="The component to open, either a path to a python file or any of []")


    if args is not None:

