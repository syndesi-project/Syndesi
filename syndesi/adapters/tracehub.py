# File : tracehub.py
# Author : Sébastien Deriaz
# License : GPL

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import struct
import json
import socket
import time

@dataclass(frozen=True)
class TraceEvent:
    """
    Base trace event
    """
    descriptor : str
    timestamp : float

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
class ReadEvent(TraceEvent):
    """
    Adapter read trace event
    """
    data : str
    t : str = field(default="read", init=False)
    length : int

@dataclass(frozen=True)
class WriteEvent(TraceEvent):
    """
    Adapter write trace event
    """
    data : str
    length : int
    t : str = field(default="write", init=False)

EVENTS : dict[str, type[TraceEvent]]= {
    e.t : e for e in [FragmentEvent, OpenEvent, CloseEvent, ReadEvent, WriteEvent]
}

DEFAULT_MULTICAST_GROUP = "239.255.42.99"
DEFAULT_MULTICAST_PORT = 12000

def json_to_trace_event(payload : dict) -> TraceEvent:
    """
    Convert json data to TraceEvent
    """
    payload_type = payload.get("t", None)
    for k, event in EVENTS.items():
        if k == payload_type:
            arguments = payload.copy()
            arguments.pop("t")
            return event(**arguments)
    raise ValueError(f"Could not parse payload : {payload}")

class _TraceHub:
    TTL = 1
    LOOPBACK = True
    TRUNCATE_LENGTH = 50

    _udp_addr = (DEFAULT_MULTICAST_GROUP, DEFAULT_MULTICAST_PORT)

    def __init__(self) -> None:
        self._udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._udp_sock.setblocking(False)
        self._udp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack("b", self.TTL))
        self._udp_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, struct.pack("b", 1 if self.LOOPBACK else 0))
        self._udp_dropped = 0

    def emit_open(self, descriptor : str):
        """
        Emit an open trace event
        """
        self._emit_event(OpenEvent(descriptor, time.time()))
    
    def emit_close(self, descriptor : str):
        """
        Emit a close trace event
        """
        self._emit_event(CloseEvent(descriptor, time.time()))

    def _truncate(self, data : bytes, encoding : str) -> str:
        return data[:self.TRUNCATE_LENGTH].decode(encoding, errors='replace')

    def emit_fragment(self, descriptor : str, data : bytes, encoding : str):
        """
        Emit a fragment trace event
        """
        self._emit_event(FragmentEvent(
            descriptor,
            time.time(),
            self._truncate(data, encoding),
            len(data)
        ))

    def emit_write(self, descriptor : str, data : bytes, encoding : str):
        """
        Emit a write trace event
        """
        self._emit_event(WriteEvent(
            descriptor,
            time.time(),
            self._truncate(data, encoding),
            len(data)
        ))

    def emit_read(self, descriptor : str, data : bytes, encoding : str):
        """
        Emit a read trace event
        """
        self._emit_event(ReadEvent(
            descriptor,
            time.time(),
            data[:self.TRUNCATE_LENGTH].decode(encoding, errors='replace'),
            len(data)
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
