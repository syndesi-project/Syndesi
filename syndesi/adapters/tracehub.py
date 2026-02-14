# File : tracehub.py
# Author : Sébastien Deriaz
# License : GPL
"""
Trace module

A single global instance of TraceHub allows all the syndesi modules and workers
to emit trace events
"""

from __future__ import annotations

import json
import socket
import struct
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from syndesi.adapters.stop_conditions import StopConditionType, Fragment

STOP_CONDITION_INDICATOR = {
    StopConditionType.CONTINUATION : "Cont",
    StopConditionType.FRAGMENT : "Frag",
    StopConditionType.LENGTH : "Len",
    StopConditionType.TERMINATION : "Term",
    StopConditionType.TOTAL : "Tot",
    StopConditionType.TIMEOUT : "Time"
}


@dataclass(frozen=True)
class TraceEvent:
    """
    Base trace event
    """
    descriptor : str
    timestamp : float
    t : str = field(default="", init=False)

@dataclass(frozen=True)
class OpenEvent(TraceEvent):
    """
    Adapter open trace event
    """
    t : str = field(default="open", init=False)

@dataclass(frozen=True)
class FragmentEvent(TraceEvent):
    """
    Fragment received trace event
    """
    data : str
    length : int
    t : str = field(default="fragment", init=False)

@dataclass(frozen=True)
class CloseEvent(TraceEvent):
    """
    Adapter close trace event
    """
    t : str = field(default="close", init=False)

@dataclass(frozen=True)
class ReadBytesEvent(TraceEvent):
    """
    Adapter read trace event
    """
    data : str
    length : int
    stop_condition_indicator : str
    t : str = field(default="bytes_read", init=False)

@dataclass(frozen=True)
class WriteEvent(TraceEvent):
    """
    Adapter write trace event
    """
    data : str
    length : int
    t : str = field(default="write", init=False)

@dataclass(frozen=True)
class ReadEvent(TraceEvent):
    """
    Generic read event
    """
    message : str
    t : str = field(default="read", init=False)

EVENTS : list[type[TraceEvent]] = [FragmentEvent, OpenEvent, CloseEvent, ReadBytesEvent, WriteEvent]

EVENTS_MAP : dict[str, type[TraceEvent]]= {
    e.t : e for e in EVENTS
}

DEFAULT_MULTICAST_GROUP = "239.255.42.99"
DEFAULT_MULTICAST_PORT = 12000

def json_to_trace_event(payload : dict[str, Any]) -> TraceEvent:
    """
    Convert json data to TraceEvent
    """
    payload_type = payload.get("t", None)
    if payload_type in EVENTS_MAP:
        arguments = payload.copy()
        arguments.pop("t")
        return EVENTS_MAP[payload_type](**arguments)

    raise ValueError(f"Could not parse payload : {payload}")

class _TraceHub:
    TTL = 1
    LOOPBACK = True
    TRUNCATE_LENGTH = 50

    _udp_addr = (DEFAULT_MULTICAST_GROUP, DEFAULT_MULTICAST_PORT)

    TRUNCATION_TERMINATION = "..."
    # CHARACTERS_REPLACEMENT = {
    #     '\n' : '\\n',
    #     '\r' : '\\r',
    #     '\t' : '\t',

    # }

    def __init__(self) -> None:
        #self._udp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        #self._udp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)

        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._udp_sock.setblocking(False)
        self._udp_sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_IF,
            socket.inet_aton("127.0.0.1")
        )
        self._udp_sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_TTL,
            struct.pack("b", self.TTL)
        )
        self._udp_sock.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_MULTICAST_LOOP,
            struct.pack("b", 1 if self.LOOPBACK else 0)
        )
        self._udp_dropped = 0

    def emit_open(self, descriptor : str) -> None:
        """
        Emit an open trace event
        """
        self._emit_event(OpenEvent(descriptor, time.time()))

    def emit_close(self, descriptor : str) -> None:
        """
        Emit a close trace event
        """
        self._emit_event(CloseEvent(descriptor, time.time()))

    def _format_bytes(self, data : bytes) -> str:
        if len(data) > 4*self.TRUNCATE_LENGTH:
            # Pre-truncate to avoid working with super long data
            data = data[:4*self.TRUNCATE_LENGTH]

        str_data = repr(data)[2:-1]

        truncated_str = str_data[:self.TRUNCATE_LENGTH]

        if len(str_data) != len(truncated_str):
            return truncated_str[:-len(self.TRUNCATION_TERMINATION)] + self.TRUNCATION_TERMINATION
        return truncated_str

    def emit_fragment(self, descriptor : str, fragment : Fragment) -> None:
        """
        Emit a fragment trace event
        """
        match fragment.data:
            case bytes():
                self._emit_event(FragmentEvent(
                    descriptor,
                    time.time(),
                    self._format_bytes(fragment.data),
                    len(fragment.data)
                ))

    def emit_write(self, descriptor : str, data : Any) -> None:
        """
        Emit a write trace event
        """
        if isinstance(data, bytes):
            self._emit_event(WriteEvent(
                descriptor,
                time.time(),
                self._format_bytes(data),
                len(data)
            ))
        else:
            # TODO : Fix
            print(f"Invalid data type for emit_write : {type(data)}")

    def emit_bytes_read(
            self,
            descriptor : str,
            data : bytes,
            stop_condition_type : StopConditionType
        ) -> None:
        """
        Emit a read trace event
        """

        indicator = STOP_CONDITION_INDICATOR[stop_condition_type]

        self._emit_event(ReadBytesEvent(
            descriptor,
            time.time(),
            self._format_bytes(data),
            len(data),
            indicator
        ))

    def emit_generic_read(
            self,
            descriptor : str,
            message : str
    ):
        self._emit_event(ReadEvent(
            descriptor,
            time.time(),
            message
        ))

    def _emit_event(self, ev: TraceEvent) -> None:
        d = asdict(ev)
        # meta = d.setdefault("meta", {})
        # if isinstance(meta, dict):
        #     meta.setdefault("pid", os.getpid())

        payload = json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

        # if len(payload) > self._udp_max:
        #     if isinstance(meta, dict):
        #         meta["truncated"] = True
        #     payload = payload[: self._udp_max]

        try:
            self._udp_sock.sendto(payload, self._udp_addr)
        except (BlockingIOError, InterruptedError, OSError):
            # drop rather than blocking I/O paths
            self._udp_dropped += 1

# Public singleton
tracehub = _TraceHub()
