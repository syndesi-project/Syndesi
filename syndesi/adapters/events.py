# File : events.py
# Author : Sébastien Deriaz
# License : GPL
"""
Adapter events

Events are emitted by the engine on the reactor thread. Callbacks must not block
"""

from dataclasses import dataclass
from typing import Generic, TypeVar

from ..component import ReadFrame, SyndesiEvent, WriteFrame
from .utils import Fragment

DataT = TypeVar("DataT")


class AdapterEvent(SyndesiEvent):
    """Adapter event"""


class AdapterOpenedEvent(AdapterEvent):
    """The adapter is now open"""


class AdapterClosedEvent(AdapterEvent):
    """The adapter is now closed, either on request or because the target went away"""


class AdapterTimeoutUpdatedEvent(AdapterEvent):
    """The adapter timeout has been changed"""


class AdapterStopConditionsUpdatedEvent(AdapterEvent):
    """The adapter stop-conditions have been changed"""


@dataclass
class AdapterWriteEvent(Generic[DataT], AdapterEvent):
    """Data has been written to the target"""

    frame: WriteFrame[DataT]


@dataclass
class AdapterFragmentEvent(Generic[DataT], AdapterEvent):
    """A fragment has been read from the backend, as returned by a single read call"""

    fragment: Fragment[DataT]
    first: bool
    next_deadline: float | None


@dataclass
class AdapterFrameEvent(Generic[DataT], AdapterEvent):
    """The framer completed a frame. buffered is True if no read was waiting for it"""

    frame: ReadFrame[DataT]
    buffered: bool


@dataclass
class AdapterReadEvent(Generic[DataT], AdapterEvent):
    """A frame has been handed to a read call"""

    frame: ReadFrame[DataT]
    from_buffer: bool


@dataclass
class AdapterBufferEvent(AdapterEvent):
    """Frames have been added to or removed from the frame buffer"""

    added_frame_ids: list[int]
    removed_frame_ids: list[int]
