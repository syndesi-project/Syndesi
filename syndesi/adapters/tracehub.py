# File : tracehub.py
# Author : Sébastien Deriaz
# License : GPL

from __future__ import annotations

from abc import abstractmethod
from dataclasses import asdict, dataclass, field
import os
import struct
import json
import socket
import time

@dataclass(frozen=True)
class TraceEvent:
    """
    Base trace event
    """

@dataclass(frozen=True)
class FragmentEvent(TraceEvent):
    """
    Fragment received trace event
    """
    data : str
    key : str = field(default="fragment", init=False)

@dataclass(frozen=True)
class OpenEvent(TraceEvent):
    """
    Adapter open trace event
    """
    key : str = field(default="open", init=False)

@dataclass(frozen=True)
class CloseEvent(TraceEvent):
    """
    Adapter close trace event
    """
    key : str = field(default="close", init=False)

@dataclass(frozen=True)
class ReadEvent(TraceEvent):
    """
    Adapter read trace event
    """
    data : str
    key : str = field(default="read", init=False)

EVENTS : dict[str, type[TraceEvent]]= {
    e.key : e for e in [FragmentEvent, OpenEvent, CloseEvent, ReadEvent]
}

DEFAULT_MULTICAST_GROUP = "239.255.42.99"
DEFAULT_MULTICAST_PORT = 12000

def json_to_trace_event(payload : dict) -> TraceEvent:
    """
    Convert json data to TraceEvent
    """
    payload_key = payload.get("key", None)
    for k, event in EVENTS.items():
        if k == payload_key:
            arguments = payload.copy()
            arguments.pop("key")
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

    def emit_open(self):
        """
        Emit an open trace event
        """
        self._emit_event(OpenEvent())
    
    def emit_close(self):
        """
        Emit a close trace event
        """
        self._emit_event(CloseEvent())

    def emit_fragment(self, data : bytes, encoding : str = 'utf-8'):
        """
        Emit a fragment trace event
        """
        self._emit_event(FragmentEvent(data[:self.TRUNCATE_LENGTH].decode(encoding, errors='replace')))

    def emit_read(self, data : bytes, encoding : str = 'utf-8'):
        """
        Emit a read trace event
        """
        self._emit_event(ReadEvent(
            data[:self.TRUNCATE_LENGTH].decode(encoding, errors='replace')
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
