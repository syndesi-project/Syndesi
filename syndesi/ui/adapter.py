# File : adapter.py
# Author : Sébastien Deriaz
# License : GPL
"""
Adapter UI elements
"""

import ast
import asyncio
import time
import traceback
from abc import ABC, abstractmethod
from typing import Any, Callable, Generic, TypeVar

import dearpygui.dearpygui as dpg  # type: ignore[import-untyped]

from syndesi.tools.errors import (
    AdapterOpenError,
    AdapterReadError,
    AdapterTimeoutError,
    AdapterWriteError,
)

from ..adapters.adapterworker import (
    AdapterBufferEvent,
    AdapterClosedEvent,
    AdapterEvent,
    AdapterFragmentEvent,
    AdapterOpenedEvent,
    AdapterFrameEvent,
    AdapterWriteEvent,
)
from ..adapters.bytesadapter import BytesAdapter
from ..adapters.ip import IP, IPDescriptor
from ..adapters.stop_conditions import (
    Continuation,
    FragmentSC,
    Length,
    StopCondition,
    StopConditionType,
    Termination,
    Total,
)
from ..component import ReadScope
from .tools import Block, StringTestingGroup, ComponentBlock, _help, _hsv_to_rgb, bytes_help

StopConditionT = TypeVar("StopConditionT", bound=StopCondition)

loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

class StopConditionBlock(Generic[StopConditionT], Block):
    """Single stop-condition block (tab)"""
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
                self._termination_input = dpg.add_input_text(
                    label="Termination",
                    width=100,
                    callback=self._termination_callback,
                    default_value=repr(self._stop_condition.sequence)[2:-1]
                )
                bytes_help()

            self._error_text = dpg.add_text("", color=(255,0,0), show=False)

        self.items += [self._termination_input, self._error_text, self.tab]

    def _termination_callback(self, _ : int | str, app_data : str) -> None:
        try:
            sequence_bytes = ast.literal_eval(f"b'{app_data}'")
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
                width=100,
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
        continuation = self.DEFAULT_CONTINUATION if stop_condition is None \
            else stop_condition.continuation
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
                width=100,
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


class BytesAdapterBlock(Generic[AdapterT], ComponentBlock, ABC):
    """BytesAdapter UI block"""
    _adapter : AdapterT
    title = ""
    #on_close : Callable[[], None] | None = None
    #on_open : Callable[[], None] | None = None
    DEFAULT_TIMEOUT = 0

    STOP_CONDITIONS = [x for x in StopConditionType if x != StopConditionType.TIMEOUT]

    def __init__(self, title : str, adapter : AdapterT, event_callback : Callable[[AdapterEvent], None]) -> None:
        self._adapter = adapter
        self._adapter.register_event_callback(self._event_callback)
        self._ui_event_callback = event_callback

        self._testing_window : StringTestingGroup | None = None

        self._status_text : int | str = 0
        self._stop_conditions_cache : list[StopConditionBlock[Any]] = []
        self._tab_bar : int | str = -1
        self._combo : int | str = -1
        self._timeout_input : int | str = -1
        self._title = title
        self._read_output : int | str = -1
        self._read_start : float = 0
        self._read_task_running = False
        self._header : int | str = -1
        self._event_window : int | str = -1
        self._events : list[int | str] = []
        
        self._add_tab : int | str = -1
        self._right_clicked_tab : StopConditionBlock[Any] | None = None
        self._buffer_items : dict[int, int | str] = {}
        self._edit_stop_condition_popup : int | str = -1
        self._add_stop_condition_popup : int | str = -1
        self._show_fragments_checkbox : int | str = -1
        self._buffer_window : int | str = -1
        self._write_input : dict[int, int | str] = {}
        self._write_group : dict[int, int | str] = {} 

    def reset(self):
        self._clear_events()
        self._adapter_to_cache_stop_conditions()
        if self._testing_window is not None:
            self._testing_window.write_status("")

    def _event_callback(self, event : AdapterEvent):
        self._ui_event_callback(event)
        if isinstance(event, AdapterBufferEvent):
            loop.call_soon_threadsafe(self._buffer_event, event)

    def _buffer_event(self, event : AdapterBufferEvent):
        if len(event.added_frame_ids) > 0:
            for frame in self._adapter.frame_buffer:
                if frame.id in event.added_frame_ids:
                    self._buffer_items[frame.id] = dpg.add_text(
                        str(frame.data),
                        parent=self._buffer_window
                    )

        for removed_frame_id in event.removed_frame_ids:
            tag = self._buffer_items.pop(removed_frame_id, None)
            if tag is not None:
                dpg.delete_item(tag)

    @abstractmethod
    def _build_descriptor(self, parent : int | str) -> None:
        ...

    def _clear_events(self) -> None:
        for tag in self._events:
            dpg.delete_item(tag)
        self._events.clear()

    def build_configuration_tab(self, parent : int | str) -> None:
        with dpg.group(parent=parent, horizontal=False):
 
            self._build_descriptor(dpg.last_item())
            self._timeout_input = dpg.add_input_float(
                label="Timeout",
                default_value=0 if self._adapter.timeout is None else self._adapter.timeout,
                width=100
            )

            dpg.add_separator()

            dpg.add_text("Stop-conditions", color=(70, 142, 194))
            with dpg.tab_bar(reorderable=True) as self._tab_bar:
                ...

            with dpg.handler_registry():
                dpg.add_mouse_click_handler(dpg.mvMouseButton_Right, callback=self._right_click)
                dpg.add_mouse_click_handler(dpg.mvMouseButton_Left, callback=self._left_click)

            self._adapter_to_cache_stop_conditions()

            dpg.add_spacer(height=10)
            dpg.add_text("Buffer")
            with dpg.child_window() as self._buffer_window:
                ...
                
    def build_testing_group(self, testing_window : int | str) -> int | str:
        self._testing_window = StringTestingGroup(self._write_callback, self._read_callback, 5)
        return self._testing_window.build(testing_window)                

    def _left_click(self) -> None:
        if self._add_tab != -1 and dpg.is_item_hovered(self._add_tab):
            dpg.show_item(self._add_stop_condition_popup)

    def _right_click(self) -> None:
        for block in self._stop_conditions_cache:
            if dpg.is_item_hovered(block.tab):
                self._right_clicked_tab = block
                dpg.show_item(self._edit_stop_condition_popup)

    def _build_tabs(self) -> None:
        slots = dpg.get_item_children(self._tab_bar)
        if isinstance(slots, dict):
            for slot in slots.values():
                for children in slot:
                    dpg.delete_item(children)

        for block in self._stop_conditions_cache:
            block.build(self._tab_bar)

        self._add_tab = dpg.add_tab(label="+", parent=self._tab_bar)

    def _read_callback(self, scope : ReadScope) -> None:
        self._read_start = time.time()
        asyncio.create_task(self._read_task())
        try:
            data = self._adapter.aread(scope=scope)
        except AdapterTimeoutError as e:
            self._read_task_running = False
            #dpg.set_value(self._read_output, f"Read timeout ({e.timeout})")
            #dpg.configure_item(self._read_output, color=(237, 117, 31))
        except AdapterReadError as e:
            self._read_task_running = False
            #dpg.set_value(self._read_output, str(e))
            #dpg.configure_item(self._read_output, color=(255,0,0))
        else:
            self._read_task_running = False
            #dpg.set_value(self._read_output, repr(data))
            #dpg.configure_item(self._read_output, color=(86, 178, 245))

    async def _read_task(self) -> None:
        self._read_task_running = True
        while self._read_task_running:
            #dpg.set_value(self._read_output, f"{time.time() - self._read_start:.3f}s")
            await asyncio.sleep(1/60)

    def _update_write_status(self, text : str, status : str = "neutral") -> None:
        if self._testing_window is not None:
            self._testing_window.write_status(text, status)

    def _write_callback(self, raw_data : str) -> None:
        try:
            data : bytes = ast.literal_eval(f"b'{raw_data}'")
        except SyntaxError as e:
            self._update_write_status(str(e), "error")
            return

        if self._adapter is None:
            self._update_write_status("Adapter has not been opened", "error")
            return

        try:
            self._adapter.write(data)
        except AdapterWriteError as e:
            self._update_write_status(str(e), "error")
        else:
            self._update_write_status(f"Written {repr(data)}", "ok")

    def _remove_stop_condition_callback(self) -> None:
        if self._right_clicked_tab is not None:
            self._stop_conditions_cache.remove(self._right_clicked_tab)
        self._build_tabs()

    def _remove_callback(self) -> None:
        self._cache_stop_conditions_to_adapter()

    def _add_default_stop_condition(
            self,
            _ : int | str,
            __ : Any,
            _type : StopConditionType
        ) -> None:
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

        block = self._add_stop_condition(stop_condition)
        self._build_tabs()
        dpg.set_value(self._tab_bar, block.tab)


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

        self._stop_conditions_cache.append(block)

        return block

    def _cache_stop_conditions_to_adapter(self) -> None:
        ...

    def _adapter_to_cache_stop_conditions(self) -> None:
        #self._clear_stop_conditions()
        self._stop_conditions_cache.clear()

        if self._adapter is not None:
            for stop_condition in self._adapter.stop_conditions:
                self._add_stop_condition(stop_condition)

        self._build_tabs()

    def close(self) -> None:
        """Close adapter"""
        if self._adapter is not None:
            self._adapter.close()

    @abstractmethod
    def open(self): ...

class IPBlock(BytesAdapterBlock[IP]):
    """IP adapter block"""
    title = "IP Adapter"
    def __init__(self, adapter : IP, event_callback : Callable[[AdapterEvent], None]) -> None:
        super().__init__("IP Adapter", adapter, event_callback)
        self._address_input : int | str = -1
        self._port_input : int | str = -1
        self._port_details : int | str = -1
        self._transport_input : int | str = -1

    def _build_descriptor(self, parent : int | str) -> None:
        dpg.add_text("Descriptor", color=(70, 142, 194), parent=parent)
        self._address_input = dpg.add_input_text(
            width=150,
            label="Address",
            default_value="",
        )
        with dpg.group(horizontal=True, parent=parent):
        #with dpg.group(horizontal=True):
            #with dpg.group(horizontal=True, parent=parent):
            self._port_input = dpg.add_input_text(width=100, label="Port", default_value="0")
            self._port_details = dpg.add_text("")
        self._transport_input = dpg.add_combo(
            parent=parent,
            label="Transport",
            items=[x.value for x in IPDescriptor.Transport],
            default_value=IPDescriptor.Transport.TCP.value,
            width=100
        )

    def open(self) -> None:
        self._adapter.open()

    def close(self) -> None:
        self._adapter.close()

    def sync_block_to_component(self):
        address = dpg.get_value(self._address_input)
        try:
            port = int(dpg.get_value(self._port_input))
        except ValueError:
            dpg.set_value(self._port_details, "Invalid port")
            return

        dpg.set_value(self._port_details, "")
        transport = IPDescriptor.Transport(dpg.get_value(self._transport_input))
        timeout = float(dpg.get_value(self._timeout_input))
        self._adapter.descriptor.address = address
        self._adapter.descriptor.port = port
        self._adapter.descriptor.transport = transport
        self._adapter.set_timeout(timeout if timeout != self.DEFAULT_TIMEOUT else None)

    def sync_component_to_block(self):
        dpg.set_value(self._address_input, self._adapter.descriptor.address)
        dpg.set_value(self._port_input, str(self._adapter.descriptor.port))
        dpg.set_value(self._transport_input, self._adapter.descriptor.transport.value)
        dpg.set_value(self._timeout_input, self._adapter.timeout)

