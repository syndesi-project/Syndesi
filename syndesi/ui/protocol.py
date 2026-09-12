# NOT YET PORTED to the backend/framer/engine/reactor architecture.
# This module still targets the removed Component/Adapter classes. It is kept
# as a reference while it gets ported, and excluded from the checkers until then
# mypy: ignore-errors
# pylint: skip-file
# ruff: noqa
# File : protocol.py
# Author : Sébastien Deriaz
# License : GPL

import ast
import asyncio
from collections.abc import Callable
from typing import Any, Awaitable, Generic, TypeVar

import dearpygui.dearpygui as dpg # type: ignore

from syndesi.adapters.adapterworker import AdapterEvent
from syndesi.component import ReadScope
from syndesi.protocols.delimited import Delimited
from syndesi.tools.errors import AdapterTimeoutError

from ..protocols.protocol import Protocol, ProtocolBufferEvent, ProtocolEvent
from .tools import ComponentBlock, StringTestingGroup

ProtocolT = TypeVar("ProtocolT", bound=Protocol[Any, Any])

N_WRITE_LINES = 5

loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

class ProtocolBlock(Generic[ProtocolT], ComponentBlock):
    _protocol : ProtocolT

class DelimitedBlock(ProtocolBlock[Delimited]):
    title : str = "Delimited"

    def __init__(self,
                 protocol : Delimited,
                 write_callback : Callable[[str], None],
                 read_callback : Callable[[str], Awaitable[None]],
                 read_fail_callback : Callable[[str], Awaitable[None]],
                 event_callback : Callable[[ProtocolEvent], None],
                 is_top_level : bool
                ) -> None:
        super().__init__(is_top_level, write_callback, read_callback, read_fail_callback)
        self._protocol = protocol
        self._protocol.register_event_callback(self._event_callback)
        self._ui_protocol_event_callback = event_callback
        self._different_receive_termination = False
        self._buffer_items : dict[int, int | str] = {}
        self._buffer_window : int | str = -1

    def _event_callback_safe(self, event : ProtocolEvent) -> None:
        self._ui_protocol_event_callback(event)
        if isinstance(event, ProtocolBufferEvent):
            if len(event.added_frame_ids) > 0:
                for frame in self._protocol.frame_buffer:
                    if frame.id in event.added_frame_ids:
                        self._buffer_items[frame.id] = dpg.add_text(
                            str(frame.data),
                            parent=self._buffer_window
                        )

            for removed_frame_id in event.removed_frame_ids:
                tag = self._buffer_items.pop(removed_frame_id, None)
                if tag is not None:
                    dpg.delete_item(tag)

    def _event_callback(self, event : ProtocolEvent) -> None:
        loop.call_soon_threadsafe(self._event_callback_safe, event)

    def build_configuration_tab(self, parent: int | str) -> None:
        with dpg.group(horizontal=False, parent=parent):
            dpg.add_text("Termination", color=(70, 142, 194))
            self._termination_input = dpg.add_input_text(width=150, callback=self.sync_block_to_component)
            dpg.add_text("Receive termination", color=(70, 142, 194))
            self._checkbox = dpg.add_checkbox(label="Different receive termination", default_value=self._different_receive_termination, callback=self._different_receive_termination_callback)
            self._receive_termination_input = dpg.add_input_text(width=150, callback=self.sync_block_to_component, show=self._different_receive_termination)

            dpg.add_spacer(height=10)
            dpg.add_text("Buffer")
            with dpg.child_window() as self._buffer_window:
                ...

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
        return StringTestingGroup(self._write_callback, self._read_callback).build(testing_window)

    def _write_callback(self, raw_data : str) -> None:
        self._protocol.write(raw_data)
        if self._is_top_level:
            self._ui_write_callback(raw_data)

    async def _read_callback(self, scope : ReadScope) -> None:
        data = await self._protocol.aread(scope=scope)
        if self._is_top_level:
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
