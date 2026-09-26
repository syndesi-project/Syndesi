"""
Syndesi module
"""

from .adapters.auto import auto_adapter, auto_async_adapter
from .adapters.ip import IP, AsyncIP
from .adapters.ipserver import AsyncIPServer, Client, IPServer
from .adapters.serialport import AsyncSerialPort, Parity, SerialPort
from .protocols.delimited import AsyncDelimited, Delimited
from .protocols.modbus import AsyncModbus, Modbus, ModbusType
from .protocols.raw import AsyncRaw, Raw
from .protocols.scpi import SCPI, AsyncSCPI

# Visa is optional, pyvisa may not be installed
try:
    from .adapters.visa import AsyncVisa, Visa

    _VISA = ["Visa", "AsyncVisa"]
except ImportError:  # pragma: no cover - optional dependency
    _VISA = []

__all__ = [
    # Adapters
    "IP",
    "AsyncIP",
    "SerialPort",
    "AsyncSerialPort",
    "Parity",
    "IPServer",
    "AsyncIPServer",
    "Client",
    "auto_adapter",
    "auto_async_adapter",
    # Protocols
    "Delimited",
    "AsyncDelimited",
    "Raw",
    "AsyncRaw",
    "SCPI",
    "AsyncSCPI",
    "Modbus",
    "AsyncModbus",
    "ModbusType",
    *_VISA,
]

# from .adapters.backend import (
#     AdapterBackend,
#     BackendDisconnectedError,
#     BackendError,
#     BackendOpenError,
#     BackendReadError,
#     BackendWriteError,
#     Descriptor,
#     SyndesiEvent,
# )
# from .adapters.engine import Engine, ReadScope
# from .adapters.events import (
#     AdapterBufferEvent,
#     AdapterClosedEvent,
#     AdapterEvent,
#     AdapterFragmentEvent,
#     AdapterFrameEvent,
#     AdapterOpenedEvent,
#     AdapterReadEvent,
#     AdapterStopConditionsUpdatedEvent,
#     AdapterTimeoutUpdatedEvent,
#     AdapterWriteEvent,
# )
# from .adapters.framer import (
#     AssembledFrame,
#     BytesFramer,
#     Frame,
#     Framer,
#     ReadFrame,
#     TrivialFramer,
#     WriteFrame,
# )
# from .adapters.ip import IPBackend, IPDescriptor
# from .adapters.reactor import Reactor, default_reactor
# from .adapters.stop_conditions import (
#     Continuation,
#     FragmentSC,
#     Length,
#     StopCondition,
#     Termination,
#     Total,
# )

# __all__ = [
#     # Backends
#     "AdapterBackend",
#     "Descriptor",
#     "IPBackend",
#     "IPDescriptor",
#     # Framing
#     "Framer",
#     "BytesFramer",
#     "TrivialFramer",
#     "Frame",
#     "WriteFrame",
#     "AssembledFrame",
#     "ReadFrame",
#     # Stop-conditions
#     "StopCondition",
#     "Continuation",
#     "FragmentSC",
#     "Length",
#     "Termination",
#     "Total",
#     # Engine and reactor
#     "Engine",
#     "ReadScope",
#     "Reactor",
#     "default_reactor",
#     # Events
#     "SyndesiEvent",
#     "AdapterEvent",
#     "AdapterOpenedEvent",
#     "AdapterClosedEvent",
#     "AdapterWriteEvent",
#     "AdapterFragmentEvent",
#     "AdapterFrameEvent",
#     "AdapterReadEvent",
#     "AdapterBufferEvent",
#     "AdapterTimeoutUpdatedEvent",
#     "AdapterStopConditionsUpdatedEvent",
#     # Errors
#     "BackendError",
#     "BackendOpenError",
#     "BackendReadError",
#     "BackendWriteError",
#     "BackendDisconnectedError",
# ]
