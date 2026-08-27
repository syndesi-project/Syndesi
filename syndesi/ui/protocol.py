# File : protocol.py
# Author : Sébastien Deriaz
# License : GPL

import ast
from collections.abc import Callable
from typing import Any, Awaitable, Generic, TypeVar

import dearpygui.dearpygui as dpg # type: ignore

from syndesi.adapters.adapterworker import AdapterEvent
from syndesi.component import ReadScope
from syndesi.protocols.delimited import Delimited
from syndesi.tools.errors import AdapterTimeoutError

from ..protocols.protocol import Protocol
from .tools import ComponentBlock, StringTestingGroup

ProtocolT = TypeVar("ProtocolT", bound=Protocol[Any, Any])

N_WRITE_LINES = 5

class ProtocolBlock(Generic[ProtocolT], ComponentBlock):
    _protocol : ProtocolT

class DelimitedBlock(ProtocolBlock[Delimited]):
    title : str = "Delimited"

    def __init__(self,
                 protocol : Delimited,
                 write_callback : Callable[[str], None],
                 read_callback : Callable[[str], Awaitable[None]],
                 read_fail_callback : Callable[[str], Awaitable[None]],
                 is_top_level : bool
                ) -> None:
        super().__init__(is_top_level, write_callback, read_callback, read_fail_callback)
        self._protocol = protocol
        self._different_receive_termination = False

    def build_configuration_tab(self, parent: int | str) -> None:
        with dpg.group(horizontal=False, parent=parent):
            dpg.add_text("Termination", color=(70, 142, 194))
            self._termination_input = dpg.add_input_text(width=150, callback=self.sync_block_to_component)
            dpg.add_text("Receive termination", color=(70, 142, 194))
            self._checkbox = dpg.add_checkbox(label="Different receive termination", default_value=self._different_receive_termination, callback=self._different_receive_termination_callback)
            self._receive_termination_input = dpg.add_input_text(width=150, callback=self.sync_block_to_component, show=self._different_receive_termination)

        self.sync_component_to_block()

    def _different_receive_termination_callback(self) -> None:
        self._different_receive_termination = dpg.get_value(self._checkbox)
        if self._different_receive_termination:
            dpg.show_item(self._receive_termination_input)
        else:
            dpg.hide_item(self._receive_termination_input)
            dpg.set_value(self._receive_termination_input, dpg.get_value(self._termination_input))

        self.sync_block_to_component()

    def build_testing_group(self, testing_window : int | str) -> int | str:
        return StringTestingGroup(self._write_callback, self._read_callback, 5).build(testing_window)

    def _write_callback(self, raw_data : str) -> None:
        if self._is_top_level:
            self._ui_write_callback(raw_data)
        self._protocol.write(raw_data)

    async def _read_callback(self, scope : ReadScope) -> None:
        try:
            data = await self._protocol.aread(scope=scope)
        except AdapterTimeoutError as e:
            await self._ui_read_fail_callback(f"Timeout ({e.timeout:.3f}s)")
        else:
            await self._ui_read_callback(data)

    def reset(self) -> None:
        self.sync_component_to_block()

    def sync_component_to_block(self) -> None:
        termination = self._protocol.termination
        receive_termination = self._protocol.receive_termination

        if termination != receive_termination:
            dpg.set_value(self._checkbox, False)

        dpg.set_value(self._termination_input, repr(termination)[1:-1])
        dpg.set_value(self._receive_termination_input, repr(receive_termination)[1:-1])

    def sync_block_to_component(self) -> None:
        termination_raw = dpg.get_value(self._termination_input)
        termination = ast.literal_eval(f"b'{termination_raw}'")
        if self._different_receive_termination:
            receive_termination_raw = dpg.get_value(self._receive_termination_input)
            receive_termination = ast.literal_eval(f"b'{receive_termination_raw}'")
        else:
            receive_termination = termination

        self._protocol.set_termination(termination, receive_termination)

    def close(self) -> None:
        self._protocol.close()

    def open(self) -> None:
        self._protocol.open()
