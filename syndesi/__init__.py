"""
Syndesi module

This branch is mid-migration to the backend/framer/engine/reactor architecture.
The user facing classes (IP, Delimited, SCPI, ...) are rebuilt on top of the
layers exported here, so only those layers are public for now
"""

from .adapters.backend import (
    AdapterBackend,
    BackendDisconnectedError,
    BackendError,
    BackendOpenError,
    BackendReadError,
    BackendWriteError,
    Descriptor,
    SyndesiEvent,
)
from .adapters.engine import Engine, ReadScope
from .adapters.events import (
    AdapterBufferEvent,
    AdapterClosedEvent,
    AdapterEvent,
    AdapterFragmentEvent,
    AdapterFrameEvent,
    AdapterOpenedEvent,
    AdapterReadEvent,
    AdapterStopConditionsUpdatedEvent,
    AdapterTimeoutUpdatedEvent,
    AdapterWriteEvent,
)
from .adapters.framer import (
    AssembledFrame,
    BytesFramer,
    Frame,
    Framer,
    ReadFrame,
    TrivialFramer,
    WriteFrame,
)
from .adapters.ip import IPBackend, IPDescriptor
from .adapters.reactor import Reactor, default_reactor
from .adapters.stop_conditions import (
    Continuation,
    FragmentSC,
    Length,
    StopCondition,
    Termination,
    Total,
)

__all__ = [
    # Backends
    "AdapterBackend",
    "Descriptor",
    "IPBackend",
    "IPDescriptor",
    # Framing
    "Framer",
    "BytesFramer",
    "TrivialFramer",
    "Frame",
    "WriteFrame",
    "AssembledFrame",
    "ReadFrame",
    # Stop-conditions
    "StopCondition",
    "Continuation",
    "FragmentSC",
    "Length",
    "Termination",
    "Total",
    # Engine and reactor
    "Engine",
    "ReadScope",
    "Reactor",
    "default_reactor",
    # Events
    "SyndesiEvent",
    "AdapterEvent",
    "AdapterOpenedEvent",
    "AdapterClosedEvent",
    "AdapterWriteEvent",
    "AdapterFragmentEvent",
    "AdapterFrameEvent",
    "AdapterReadEvent",
    "AdapterBufferEvent",
    "AdapterTimeoutUpdatedEvent",
    "AdapterStopConditionsUpdatedEvent",
    # Errors
    "BackendError",
    "BackendOpenError",
    "BackendReadError",
    "BackendWriteError",
    "BackendDisconnectedError",
]
