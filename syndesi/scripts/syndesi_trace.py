# File : syndesi_trace.py
# Author : Sébastien Deriaz
# License : GPL
"""
CLI viewer for Syndesi trace events (UDP).

This tool allows the user to see what's going inside syndesi while it's running in another process

Usage :

syndesi-trace [--mode MODE]

Modes
-----
- interactive (default): tabs per adapter, switch with ←/→ (or h/l), quit with q.
- flat: append-only timeline (stdout or --output file).
"""
from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from types import TracebackType
import argparse
import json
import os
import selectors
import socket
import struct
import sys
from collections import OrderedDict, deque
from collections.abc import Generator
from typing import Any, TYPE_CHECKING
from fnmatch import fnmatchcase
import termios
import tty

from syndesi.adapters.tracehub import (
    DEFAULT_MULTICAST_GROUP,
    DEFAULT_MULTICAST_PORT,
    CloseEvent,
    FragmentEvent,
    OpenEvent,
    ReadEvent,
    TraceEvent,
    WriteEvent,
    json_to_trace_event,
)

if TYPE_CHECKING:
    from rich.align import Align
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
    rich_available = True
else:
    try:
        from rich.align import Align
        from rich.console import Console
        from rich.live import Live
        from rich.panel import Panel
        from rich.text import Text
        rich_available = True
    except ImportError:
        rich_available = False

class TraceMode(StrEnum):
    """Trace mode"""
    INTERACTIVE = 'interactive'
    FLAT = 'flat'

class TimeMode(StrEnum):
    """Time display mode"""
    ABSOLUTE = 'abs'
    RELATIVE = 'rel'

# -----------------------------
# Terminal input (interactive)
# -----------------------------

#pylint: disable=too-many-instance-attributes
class Trace:
    """Trace viewer base class"""
    ADAPTER_STYLES = ["cyan", "magenta", "green", "yellow", "blue", "bright_cyan",
            "bright_magenta", "bright_green"]
    def __init__(
            self,
            *,
            group : str,
            port : int,
            descriptor_filter : str,
            time_mode : str,
            no_fragments : bool
        ) -> None:
        self.group = group
        self.port = port

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", self.port))
        mreq = struct.pack("4s4s", socket.inet_aton(self.group), socket.inet_aton("127.0.0.1"))
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self._sock.setblocking(False)

        self._selector = selectors.DefaultSelector()
        self._selector.register(self._sock, selectors.EVENT_READ, data="udp")

        self._descriptor_filter = descriptor_filter.lower()

        self._console = Console()

        self._no_fragments = no_fragments

        self._adapters: OrderedDict[str, AdapterProperties] = OrderedDict()

        # Time
        self._time_mode = TimeMode(time_mode)
        self._first_event_timestamp : float | None = None

    @abstractmethod
    def run(self) -> None:
        """Base run method"""

    def close(self) -> None:
        """Close the trace viewer"""
        self._selector.unregister(self._sock)
        try:
            self._sock.close()
        except OSError:
            pass

    def _allow_descriptor(self, name: str) -> bool:
        return fnmatchcase(name.lower(), self._descriptor_filter)

    def get_event(self, timeout : float | None) -> Generator[TraceEvent | None, Any, Any]:
        """Return an event or None if something else triggered the selector"""
        events = self._selector.select(timeout=timeout)
        for key, _ in events:
            if key.data == "udp":
                while True:
                    try:
                        data, _addr = self._sock.recvfrom(65535)
                    except BlockingIOError:
                        break

                    json_data = json.loads(data.decode("utf-8", "replace"))
                    # Parse data
                    yield json_to_trace_event(json_data)
            else:
                yield None

    def _time_prefix(self, event : TraceEvent) -> str:
        if self._first_event_timestamp is None:
            self._first_event_timestamp = event.timestamp

        if self._time_mode == TimeMode.RELATIVE:
            relative_time = event.timestamp - self._first_event_timestamp
            return f'{relative_time:+8.3f}s'
        if self._time_mode == TimeMode.ABSOLUTE:
            return f'{event.timestamp:.3f}s'
        raise ValueError(f"Invalid time mode : {self._time_mode}")


    def _format_entry(self, event : TraceEvent, display_descriptor : bool = False) -> Text | None:
        fragments = [Text(self._time_prefix(event), style="dim"), Text(" ")]

        adapter = self._adapters[event.descriptor]

        if display_descriptor:
            fragments += [
                Text(event.descriptor, style="dim"),
                Text(" ")
            ]

        #last_write : float | None = None#self._adapter_last_write.get(event.descriptor, None)

        if isinstance(event, OpenEvent):
            fragments.append(
                Text("open  ●", style="bold green")
            )
        elif isinstance(event, CloseEvent):
            fragments.append(
                Text("close ●", style="bold red")
            )

        elif isinstance(event, WriteEvent):
            adapter.last_write_timestamp = event.timestamp
            #self._adapter_last_write[event.descriptor] = event.timestamp
            fragments += [
                Text("write →", style="bold dim"),
                Text(f"{event.length:4d}B", style="dim"),
                Text(f" {event.data}")
            ]
        elif isinstance(event, FragmentEvent):
            if self._no_fragments:
                return None
            fragments += [
                Text("      ↓", style="dim"),
                Text(f"{event.length:4d}B ", style="dim"),
                Text(event.data, style="dim"),
                Text(" (frag)", style="dim")
            ]
            if adapter.last_write_timestamp is not None:
                write_delta = event.timestamp - adapter.last_write_timestamp
                fragments.append(
                    Text(f" {write_delta:+.3f}s", style="dim")
                )
        elif isinstance(event, ReadEvent):
            fragments += [
                Text("read  ←", style="bold dim"),
                Text(f"{event.length:4d}B ", style="dim"),
                Text(f"{event.data} "),
                Text(f'({event.stop_condition_indicator})', style="dim")
            ]
            if adapter.last_write_timestamp is not None:
                write_delta = event.timestamp - adapter.last_write_timestamp
                fragments.append(
                    Text(f" {write_delta:+.3f}s", style="dim")
                )
        else:
            fragments += [
                Text("ERROR", style="bold red")
            ]

        return Text.assemble(
            *fragments
        )

    def _next_style(self) -> str:
        color = self.ADAPTER_STYLES[len(self._adapters) % len(self.ADAPTER_STYLES)]
        return color

    def ingest(self, event : TraceEvent, max_events : int = 0) -> bool:
        """Ingest event"""
        if not self._allow_descriptor(event.descriptor):
            return False

        if event.descriptor not in self._adapters:
            self._adapters[event.descriptor] = AdapterProperties(
                blocks=deque([], max_events) if max_events > 0 else None,
                style=self._next_style()
            )
        return True

class FlatTrace(Trace):
    """Flat trace (stdout or file)"""
    def __init__(
            self,
            *,
            group: str,
            port: int,
            time_mode : str,
            descriptor_filter : str,
            no_fragments : bool,
            output: str | None
        ) -> None:
        super().__init__(
            group=group,
            port=port,
            descriptor_filter=descriptor_filter,
            time_mode=time_mode,
            no_fragments=no_fragments
        )

        # pylint: disable=consider-using-with
        self._output_fh = open(output, "a", encoding="utf-8") if output else None

    class CSVColumn(StrEnum):
        """Name of CSV columns"""
        DESCRIPTOR = "descriptor"
        TIME = "time"
        EVENT = "event"
        SIZE = "size"
        DATA = "data"
        STOP_CONDITION = "stop_condition"

    def run(self) -> None:
        # No live UI; just print as events arrive.
        while True:
            for event in self.get_event(None):
                if event is not None and self._allow_descriptor(event.descriptor):
                    if self._output_fh is not None:
                        file_event = self._format_file_entry(event)
                        if file_event is not None:
                            self._output_fh.write(file_event)
                    self.ingest(event)#self.print_event(event)

    def _format_file_entry(self, event : TraceEvent) -> str | None:
        columns : OrderedDict[FlatTrace.CSVColumn, str] = OrderedDict(
            {k : "" for k in self.CSVColumn}
        )

        if isinstance(event, FragmentEvent) and self._no_fragments:
            return None

        columns[self.CSVColumn.DESCRIPTOR] = event.descriptor
        columns[self.CSVColumn.TIME] = f"{event.timestamp:.6f}"
        columns[self.CSVColumn.EVENT] = event.t

        if isinstance(event, (WriteEvent, ReadEvent, FragmentEvent)):
            columns[self.CSVColumn.DATA] = event.data
            columns[self.CSVColumn.SIZE] = str(event.length)

            if isinstance(event, ReadEvent):
                columns[self.CSVColumn.STOP_CONDITION] = event.stop_condition_indicator

        return ','.join(columns.values()) + '\n'

    def close(self) -> None:
        if self._output_fh:
            try:
                self._output_fh.flush()
                self._output_fh.close()
            except OSError:
                pass
            self._output_fh = None
        super().close()

    def _print_header(self) -> None:
        hdr = f"# syndesi-trace flat mode | host={self.group} port={self.port}"
        print(hdr)

    def print_event(self, event : TraceEvent) -> None:
        """Print event to the console"""
        output = self._format_entry(event, display_descriptor=True)
        if output is not None:
            self._console.print(output)

class InteractiveTrace(Trace):
    """Interactive trace with tabs for each adapter"""


    def __init__(
            self,
            *,
            group: str,
            port: int,
            time_mode : str,
            descriptor_filter: str,
            no_fragments : bool,
            max_events: int
            ) -> None:
        super().__init__(
            group=group,
            port=port,
            descriptor_filter=descriptor_filter,
            time_mode=time_mode,
            no_fragments=no_fragments
        )

        if Console is None:
            print("This viewer requires 'rich'. Install it with: pip install rich", file=sys.stderr)
            raise SystemExit(2)

        self._use_stdin = os.name == "posix"
        if self._use_stdin:
            self._selector.register(sys.stdin, selectors.EVENT_READ, data="stdin")

        self._selected_idx: int = 0

        self.max_events = max_events

        self._scroll_offset : int = 0
        self._auto_follow : bool = True


    def _handle_key(self, token: str) -> bool:
        # returns False to quit
        token = token.strip()
        if token in ("q", "Q"):
            return False
        if token in ("LEFT", "h"):

            if self._adapters:
                self._selected_idx = (self._selected_idx - 1) % len(self._adapters)
        if token in ("RIGHT", "l"):
            if self._adapters:
                self._selected_idx = (self._selected_idx + 1) % len(self._adapters)
        if token in ("UP", "k"):
            if self._adapters:
                #st = self.adapters[self.adapter_order[self.selected_idx]]
                self._auto_follow = False
                self._scroll_offset += 1
        if token in ("DOWN", "j"):
            if self._adapters:
                #st = self.adapters[self.adapter_order[self.selected_idx]]
                if self._scroll_offset > 0:
                    self._scroll_offset -= 1
                if self._scroll_offset == 0:
                    self._auto_follow = True
        return True

    def run(self) -> None:
        with _TerminalRawMode():
            with Live(self._render_interactive(), refresh_per_second=20, screen=True) as live:
                running = True
                while running:

                    for event in self.get_event(timeout=0.05):
                        if event is None:
                            for k in _read_keys_nonblocking():
                                running = self._handle_key(k)
                                if not running:
                                    break
                        else:
                            self.ingest(event)

                    if os.name == "nt":
                        for k in _read_keys_nonblocking():
                            running = self._handle_key(k)
                            if not running:
                                break

                    live.update(self._render_interactive())
                    if not running:
                        break

    def ingest(self, event : TraceEvent, max_events : int = 0) -> bool:
        """Manage an incoming event"""
        if not super().ingest(event, self.max_events):
            return False

        adapter = self._adapters[event.descriptor]

        block = self._format_entry(event)
        if block is not None:
            if adapter.blocks is not None:
                adapter.blocks.append(block)

        return True

    def _render_tabs(self) -> Text:
        t = Text()
        t.append("Adapters: ", style="dim")
        if self._adapters:
            for i, (name, adapter) in enumerate(self._adapters.items()):
                if i == self._selected_idx:
                    style = f"bold reverse {adapter.style}"
                else:
                    style = f"{adapter.style}"
                t.append(f" {name} ", style=style)
        else:
            t.append("(no adapters)")

        t.append("   ", style="dim")
        t.append("←/→ switch  ↑/↓ scroll  q quit  (h/j/k/l also)", style="dim")
        return t

    def _render_interactive(self) -> Panel:
        if not self._adapters:
            body = Text("Waiting for events…", style="dim")
            return Panel(Align.left(body), title="Syndesi Trace", border_style="dim")

        # Compose recent blocks into lines
        lines: list[Text] = []
        selected_adapter = list(self._adapters.values())[self._selected_idx]
        if selected_adapter.blocks is not None:
            for block in selected_adapter.blocks:
                lines.append(block)

        if not lines:
            lines = [Text("No events yet for this adapter.", style="dim")]

        body = Text("\n").join(self._visible_lines(lines))
        header = self._render_tabs()

        # Wrap body in a panel; header goes as title-ish via subtitle
        return Panel(
            Align.left(body),
            title=header,
            border_style="bright_black",
            padding=(1, 1),
        )

    def _visible_lines(self, lines: list[Text]) -> list[Text]:
        height = self._console.size.height if self._console is not None else 24
        # Reserve space for borders, title, and padding.
        visible = max(1, height - 6)
        total = len(lines)
        max_offset = max(0, total - visible)

        if self._auto_follow:
            self._scroll_offset = 0
        else:
            self._scroll_offset = min(max_offset, self._scroll_offset)
        start = max(0, total - visible - self._scroll_offset)
        return lines[start:start + visible]

class _TerminalRawMode:
    """Best-effort cbreak/raw mode (POSIX). Windows falls back to polling msvcrt."""
    def __init__(self) -> None:
        self._enabled = False
        self._old : list[Any] | None = None

    def __enter__(self) -> _TerminalRawMode:
        if os.name != "posix":
            return self
        try:
            fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            self._enabled = True
        except OSError:
            self._enabled = False
        return self

    def __exit__(
            self,
            type_: type[BaseException] | None,
            value: BaseException | None,
            traceback: TracebackType | None
        ) -> None:
        if os.name != "posix":
            return
        if not self._enabled or self._old is None:
            return
        try:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old)
        except OSError:
            pass

def _read_keys_nonblocking() -> list[str]:
    """
    Read available keys without blocking.
    Returns a list of key tokens: "LEFT", "RIGHT", "q", etc.
    """
    keys: list[str] = []

    if os.name == "nt":
        raise NotImplementedError()
        # try:
        #     import msvcrt
        #     while msvcrt.kbhit():
        #         ch = msvcrt.getwch()
        #         if ch in ("\x00", "\xe0"):  # special key prefix
        #             ch2 = msvcrt.getwch()
        #             if ch2 == "K":
        #                 keys.append("LEFT")
        #             elif ch2 == "M":
        #                 keys.append("RIGHT")
        #             elif ch2 == "H":
        #                 keys.append("UP")
        #             elif ch2 == "P":
        #                 keys.append("DOWN")
        #         else:
        #             keys.append(ch)
        # except Exception:
        #     return keys
        # return keys

    # POSIX: stdin will be readable via selectors. We still decode escape sequences here.
    try:
        data = os.read(sys.stdin.fileno(), 64)
    except OSError:
        return keys

    if not data:
        return keys

    s = data.decode("utf-8", "ignore")
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\x1b":  # escape
            # Arrow keys: ESC [ D/C
            if i + 2 < len(s) and s[i + 1] == "[":
                code = s[i + 2]
                if code == "D":
                    keys.append("LEFT")
                    i += 3
                    continue
                if code == "C":
                    keys.append("RIGHT")
                    i += 3
                    continue
                if code == "A":
                    keys.append("UP")
                    i += 3
                    continue
                if code == "B":
                    keys.append("DOWN")
                    i += 3
                    continue
            i += 1
            continue
        keys.append(ch)
        i += 1

    return keys

# -----------------------------
# Viewer state
# -----------------------------

@dataclass
class AdapterProperties:
    """Adapter state class"""
    blocks : deque[Text] | None
    style : str
    last_write_timestamp: float | None = None


# -----------------------------
# Main loop
# -----------------------------

DEFAULT_MAX_EVENTS = 1000

def main(argv: list[str] | None = None) -> None:
    """Main syndesi-trace entry-point"""

    parser = argparse.ArgumentParser(
        prog="syndesi-trace",
        description="Live console viewer for Syndesi trace events (UDP)."
    )

    parser.add_argument(
        "--mode",
        choices=[str(x) for x in TraceMode],
        default=TraceMode.INTERACTIVE.value,
        help="Display mode. interactive: tabs per adapter. flat: append-only timeline.",
    )

    # Network
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_MULTICAST_PORT,
        help="UDP port to bind (default: 12000)."
    )
    parser.add_argument(
        "--group",
        default=DEFAULT_MULTICAST_GROUP,
        help="If set, join this UDP multicast group "\
            "(enables true pub/sub without producer client management).",
    )

    # Filtering
    parser.add_argument(
        "--filter",
        default="*",
        type=str,
        help="Filter which adapters are displayed"
    )

    # Time
    parser.add_argument(
        "--time",
        dest="time_mode",
        choices=[str(x) for x in TimeMode],
        default=TimeMode.RELATIVE.value,
        help="Time display: rel = relative to adapter open/first seen, "\
            "abs = absolute timestamp")

    # Content verbosity
    parser.add_argument(
        "--no-frag",
        action="store_true",
        help="Disable fragment display"
    )
    parser.add_argument(
        "--max-events",
        type=int,
        default=DEFAULT_MAX_EVENTS,
        help="Max event blocks kept per adapter in interactive mode (0 = unlimited)."
    )

    # Output (flat)
    parser.add_argument(
        "--output",
        default=None,
        help="Write flat output to this file instead of stdout."
    )

    args = parser.parse_args(argv)

    mode = TraceMode(args.mode)

    trace : Trace

    if mode == TraceMode.INTERACTIVE:
        trace = InteractiveTrace(
            group=args.group,
            port=args.port,
            time_mode=args.time_mode,
            descriptor_filter=args.filter,
            no_fragments=args.no_frag,
            max_events=args.max_events
        )
    elif mode == TraceMode.FLAT:
        trace = FlatTrace(
            group=args.group,
            port=args.port,
            time_mode=args.time_mode,
            descriptor_filter=args.filter,
            no_fragments=args.no_frag,
            output=args.output
        )
    else:
        raise ValueError(f'Invalid mode : {mode}')

    try:
        trace.run()
    except KeyboardInterrupt:
        pass
    finally:
        trace.close()

if __name__ == "__main__":
    main()
