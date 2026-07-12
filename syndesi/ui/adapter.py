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
from abc import abstractmethod
from typing import Any, Generic, TypeVar

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
    AdapterReadEvent,
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
from .tools import Block, Tab, _help, _hsv_to_rgb

StopConditionT = TypeVar("StopConditionT", bound=StopCondition)

loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()


def bytes_help() -> None:
    _help("bytes formatting can be used such as \\n and \\r")

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


class BytesAdapterBlock(Generic[AdapterT], Tab):
    """BytesAdapter UI block"""
    _adapter : AdapterT
    title = ""
    #on_close : Callable[[], None] | None = None
    #on_open : Callable[[], None] | None = None
    DEFAULT_TIMEOUT = 0

    STOP_CONDITIONS = [x for x in StopConditionType if x != StopConditionType.TIMEOUT]

    N_WRITE_LINES = 5

    def __init__(self, title : str, adapter : AdapterT) -> None:
        self._adapter = adapter
        self._adapter.register_event_callback(self._on_adapter_event)

        self._status_text : int | str = 0
        self._stop_conditions_cache : list[StopConditionBlock[Any]] = []
        self._tab_bar : int | str = -1
        self._combo : int | str = -1
        self._timeout_input : int | str = -1
        self._title = title
        self._write_status : int | str = -1
        self._read_output : int | str = -1
        self._read_start : float = 0
        self._read_task_running = False
        self._header : int | str = -1
        self._event_window : int | str = -1
        self._events : list[int | str] = []
        self._event_group : int | str = -1
        self._start_timestamp = time.time()
        self._add_tab : int | str = -1
        self._right_clicked_tab : StopConditionBlock[Any] | None = None
        self._buffer_items : dict[int, int | str] = {}
        self._edit_stop_condition_popup : int | str = -1
        self._add_stop_condition_popup : int | str = -1
        self._show_fragments_checkbox : int | str = -1
        self._buffer_group : int | str = -1
        self._write_input : dict[int, int | str] = {}
        self._write_group : dict[int, int | str] = {}

        self._event_queue : asyncio.Queue[AdapterEvent] = asyncio.Queue()

        asyncio.ensure_future(self.loop())

    def reset(self):
        self._clear_events()
        self._start_timestamp = time.time()
        self._adapter_to_cache_stop_conditions()
        dpg.set_value(self._write_status, "")

    @abstractmethod
    def _build_descriptor(self, parent : int | str) -> None:
        ...

    async def loop(self) -> None:
        """
        Event display loop
        """
        try:
            while True:
                event = await self._event_queue.get()
                delta = event.timestamp - self._start_timestamp
                color = (255, 255, 255)
                text : str | None = None
                if isinstance(event, AdapterClosedEvent):
                    text = "● closed"
                    color = (207, 19, 19)
                elif isinstance(event, AdapterOpenedEvent):
                    text = "● open"
                    color=(30, 199, 38)
                elif isinstance(event, AdapterReadEvent):
                    text = f"← read  {event.frame.data!r}"
                elif isinstance(event, AdapterFragmentEvent) and \
                    dpg.get_value(self._show_fragments_checkbox):
                    first_indicator = "*" if event.first else ""
                    text = f"↓    {event.fragment} ({first_indicator}frag)"
                elif isinstance(event, AdapterWriteEvent):
                    text = f"→ write {event.frame.data!r}"
                elif isinstance(event, AdapterBufferEvent):
                    if self._adapter is not None:
                        if len(event.added_frame_ids) > 0:
                            for frame in self._adapter.frame_buffer:
                                if frame.id in event.added_frame_ids:
                                    self._buffer_items[frame.id] = dpg.add_text(
                                        str(frame.data),
                                        parent=self._buffer_group
                                    )

                        for removed_frame_id in event.removed_frame_ids:
                            tag = self._buffer_items.pop(removed_frame_id, None)
                            if tag is not None:
                                dpg.delete_item(tag)
                else:
                    text = "Unknown event"
                    color = (255, 0, 0)

                if text is not None:
                    event_tag = dpg.add_group(horizontal=True, parent=self._event_group)
                    dpg.add_text(f"{delta:+8.3f} ", color=(127, 127, 127), parent=event_tag)
                    dpg.add_text(text, color=color, parent=event_tag)
                    self._events.append(event_tag)

        except Exception:
            print(f'Exception in loop : {traceback.format_exc()}')


    def _clear_events(self) -> None:
        for tag in self._events:
            dpg.delete_item(tag)
        self._events.clear()

    def _write_advanced_callback(self, sender : int | str, enabled : bool) -> None:
        for i in range(1, self.N_WRITE_LINES):
            if enabled:
                dpg.show_item(self._write_group[i])
            else:
                dpg.hide_item(self._write_group[i])

    def build(self, parent : int | str) -> None:
        with dpg.group(parent=parent):
            with dpg.handler_registry():
                dpg.add_mouse_click_handler(dpg.mvMouseButton_Right, callback=self._right_click)
                dpg.add_mouse_click_handler(dpg.mvMouseButton_Left, callback=self._left_click)

            with dpg.collapsing_header(
                label=self._title,
                default_open=True
            ) as self._header:
                with dpg.table(header_row=False, resizable=False,
                            policy=dpg.mvTable_SizingStretchSame):
                    dpg.add_table_column()
                    dpg.add_table_column()

                    with dpg.table_row():
                        with dpg.table_cell():
                            with dpg.group(horizontal=False):
                                self._build_descriptor(dpg.last_item())
                                self._timeout_input = dpg.add_input_float(
                                    label="Timeout",
                                    default_value=self.DEFAULT_TIMEOUT,
                                    width=100
                                )
                        with dpg.table_cell():
                            with dpg.group(horizontal=True):
                                dpg.add_spacer(width=5)
                                with dpg.group(horizontal=False):
                                    dpg.add_text("Stop-conditions", color=(70, 142, 194))
                                    with dpg.tab_bar(reorderable=True) as self._tab_bar:
                                        ...

                dpg.add_spacer(height=5)
                dpg.add_separator()
                dpg.add_spacer(height=5)


                dpg.add_checkbox(label="Show events", callback=self._show_events_callback, default=True)
                with dpg.child_window(height=-1, width=-1) as self._read_write_window:
                    # W -> : 
                    # R <- : 
                    # Q -> :
                    # Q <- :
                    ...






                
                #dpg.add_text("Write", color=(70, 142, 194))
                dpg.add_checkbox(label="Advanced", callback=self._write_advanced_callback)

                self._write_input = {}
                self._write_group = {}

                with dpg.group(horizontal=True):
                    with dpg.group(horizontal=False):
                        for i in range(self.N_WRITE_LINES):
                            with dpg.group(horizontal=True, show=i==0):
                                self._write_group[i] = dpg.last_item()
                                dpg.add_button(
                                    label="Write",
                                    callback=self._write_callback,
                                    user_data=i,
                                    width=100
                                )
                                self._write_input[i] = dpg.add_input_text()
                                if i == 0:
                                    bytes_help()
                self._write_status = dpg.add_text("")

                with dpg.group(horizontal=True):
                    with dpg.group(horizontal=False):
                        dpg.add_text("Read", color=(70, 142, 194))
                        dpg.add_combo(
                            label="Scope",
                            items=[x for x in ReadScope],
                            width=132,
                            default_value=ReadScope.BUFFERED.value
                        )
                        dpg.add_button(label="Read", callback=self._read_callback, width=60)
                        self._read_output = dpg.add_text("")
                    dpg.add_spacer(width=20)
                    with dpg.group(horizontal=False):
                        dpg.add_text("Buffer")
                        with dpg.child_window(height=200):
                            self._buffer_group = dpg.add_group(horizontal=False)

                dpg.add_text("Events", color=(70, 142, 194))
                with dpg.group(horizontal=True):
                    self._show_fragments_checkbox = dpg.add_checkbox(
                        label="Show fragments",
                        default_value=True
                    )
                    dpg.add_button(label="Clear events", callback=self._clear_events)
                with dpg.child_window(height=-1, width=-1) as self._event_window:
                    with dpg.theme() as tight:
                        with dpg.theme_component(dpg.mvAll):
                            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 1)  # 1px vertical

                    with dpg.group(width=-1) as self._event_group:
                        ...

                    dpg.bind_item_theme(self._event_group, tight)

                with dpg.popup(self._header) as self._add_stop_condition_popup:
                    for stop_condition in self.STOP_CONDITIONS:
                        dpg.add_selectable(
                            label=stop_condition.value,
                            callback=self._add_default_stop_condition,
                            user_data=stop_condition
                        )

                with dpg.popup(self._header) as self._edit_stop_condition_popup:
                    dpg.add_selectable(
                        label="Delete",
                        callback=self._remove_stop_condition_callback
                    )

            self._adapter_to_cache_stop_conditions()

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

    async def _read_callback(self) -> None:
        if self._adapter is None:
            return
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
        while self._read_task_running:
            dpg.set_value(self._read_output, f"{time.time() - self._read_start:.3f}s")
            await asyncio.sleep(1/60)

    def _update_write_status(self, text : str, status : str = "neutral") -> None:
        if status == "ok":
            dpg.configure_item(self._write_status, color=(30, 199, 38))
        elif status == "error":
            dpg.configure_item(self._write_status, color=(255,0,0))
        else:
            dpg.configure_item(self._write_status, color=(255,255,255))
        dpg.set_value(self._write_status, text)

    def _write_callback(self, _ : int | str, __ : Any, index : int) -> None:
        try:
            data : bytes = ast.literal_eval(f"b'{dpg.get_value(self._write_input[index])}'")
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
            t_delta = time.time() - self._start_timestamp
            self._update_write_status(f"Written {repr(data)} at {t_delta:+.3f}s", "ok")

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

    def _on_adapter_event(self, event : AdapterEvent) -> None:
        loop.call_soon_threadsafe(self._event_queue.put_nowait, event)

class IPBlock(BytesAdapterBlock[IP]):
    """IP adapter block"""
    title = "IP Adapter"
    def __init__(self, adapter : IP) -> None:
        super().__init__("IP Adapter", adapter)
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
            self._port_input = dpg.add_input_text(width=100, label="Port", default_value=0)
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

        dpg.set_value(self._port_details, "")
        transport = IPDescriptor.Transport(dpg.get_value(self._transport_input))
        timeout = float(dpg.get_value(self._timeout_input))
        self._adapter.descriptor.address = address
        self._adapter.descriptor.port = port
        self._adapter.descriptor.transport = transport
        self._adapter.set_timeout(timeout if timeout != self.DEFAULT_TIMEOUT else None)

