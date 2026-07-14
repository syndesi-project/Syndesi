# File : protocol.py
# Author : Sébastien Deriaz
# License : GPL

from typing import Any, Generic, TypeVar

from syndesi.adapters.adapter import Adapter
from syndesi.protocols.delimited import Delimited
from .tools import Tab
from ..protocols.protocol import Protocol
import dearpygui.dearpygui as dpg

#AdapterT = TypeVar("AdapterT", bound=Adapter)

ProtocolT = TypeVar("ProtocolT", bound=Protocol[Any, Any])

N_WRITE_LINES = 5

class ProtocolBlock(Generic[ProtocolT], Tab):
    title : str = ""
    _protocol : ProtocolT


class DelimitedBlock(ProtocolBlock[Delimited]):
    title : str = "Delimited"
    
    def __init__(self, protocol : Delimited) -> None:
        super().__init__()
        self._protocol = protocol

    def build_configuration_tab(self, parent: int | str) -> None:
        with dpg.group(parent=parent):
            dpg.add_text("Write", color=(70, 142, 194))
            # dpg.add_checkbox(label="Advanced", callback=self._write_advanced_callback)

            # self._write_input = {}
            # self._write_group = {}

            # with dpg.group(horizontal=True):
            #     with dpg.group(horizontal=False):
            #         for i in range(self.N_WRITE_LINES):
            #             with dpg.group(horizontal=True, show=i==0):
            #                 self._write_group[i] = dpg.last_item()
            #                 dpg.add_button(
            #                     label="Write",
            #                     callback=self._write_callback,
            #                     user_data=i,
            #                     width=100
            #                 )
            #                 self._write_input[i] = dpg.add_input_text()
            #                 if i == 0:
            #                     bytes_help()
            # self._write_status = dpg.add_text("")

            # with dpg.group(horizontal=True):
            #     with dpg.group(horizontal=False):
            #         dpg.add_text("Read", color=(70, 142, 194))
            #         dpg.add_combo(
            #             label="Scope",
            #             items=[x for x in ReadScope],
            #             width=132,
            #             default_value=ReadScope.BUFFERED.value
            #         )
            #         dpg.add_button(label="Read", callback=self._read_callback, width=60)
            #         self._read_output = dpg.add_text("")
            #     dpg.add_spacer(width=20)
            #     with dpg.group(horizontal=False):
            #         dpg.add_text("Buffer")
            #         with dpg.child_window(height=200):
            #             self._buffer_group = dpg.add_group(horizontal=False)

            # dpg.add_text("Events", color=(70, 142, 194))
            # with dpg.group(horizontal=True):
            #     self._show_fragments_checkbox = dpg.add_checkbox(
            #         label="Show fragments",
            #         default_value=True
            #     )
            #     dpg.add_button(label="Clear events", callback=self._clear_events)
            # with dpg.child_window(height=-1, width=-1) as self._event_window:
            #     with dpg.theme() as tight:
            #         with dpg.theme_component(dpg.mvAll):
            #             dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 1)  # 1px vertical

            #     with dpg.group(width=-1) as self._event_group:
            #         ...

            #     dpg.bind_item_theme(self._event_group, tight)

            # with dpg.popup(self._header) as self._add_stop_condition_popup:
            #     for stop_condition in self.STOP_CONDITIONS:
            #         dpg.add_selectable(
            #             label=stop_condition.value,
            #             callback=self._add_default_stop_condition,
            #             user_data=stop_condition
            #         )

            # with dpg.popup(self._header) as self._edit_stop_condition_popup:
            #     dpg.add_selectable(
            #         label="Delete",
            #         callback=self._remove_stop_condition_callback
            #     )

            #     self._adapter_to_cache_stop_conditions()

    def build_testing_group(self):
        ...

    def reset(self):
        ...