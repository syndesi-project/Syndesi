# File : syndesi_trace.py
# Author : Sébastien Deriaz
# License : GPL

from __future__ import annotations

from abc import abstractmethod
from enum import StrEnum
from types import TracebackType

# import json
# import socket
# import struct
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

# TRUNCATE_LENGTH = 20

# def _truncate_string(input_string : str):
#     utf16_string = input_string.encode('utf-16')
#     return utf16_string[:TRUNCATE_LENGTH*2].decode('utf-16')

# def main(group: str = DEFAULT_MULTICAST_GROUP, port : int = DEFAULT_MULTICAST_PORT) -> None:
#     sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
#     sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#     sock.bind(("0.0.0.0", port))

#     mreq = struct.pack("4s4s", socket.inet_aton(group), socket.inet_aton("0.0.0.0"))
#     sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

#     print(f"[syndesi-trace] subscribed to udp://{group}:{port}")
#     while True:
#         data, _ = sock.recvfrom(65535)
#         ev = json.loads(data.decode("utf-8", "replace"))
#         event = json_to_trace_event(ev)
#         print(event)

#!/usr/bin/env python3
"""
syndesi_trace.py

CLI viewer for Syndesi trace events (UDP).

Modes
-----
- interactive (default): tabs per adapter, switch with ←/→ (or h/l), quit with q.
- flat: append-only timeline (stdout or --output file).

Expected incoming datagram
--------------------------
A JSON object with (flexible) keys. Recommended keys:
- kind: "open" | "close" | "fragment" | "read" | "tx" | "write" | "error" | ...
- timestamp: float (monotonic or epoch). Also supports "t".
- adapter: str (also supports "adapter_id")
- data: str (already preview text) OR data_b64 OR data_hex
- data_len / nbytes: int (optional)
- stop_reason / stop_condition / stop: str|dict (for read)
- meta: dict (optional)

This viewer is intentionally tolerant: it will render best-effort.
"""

import argparse
import json
import os
import re
import selectors
import socket
import struct
import sys
from collections import deque
from collections.abc import Generator
from typing import Any

try:
    from rich.align import Align
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
except Exception:  # pragma: no cover
    Console = None  # type: ignore

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text


class TraceMode(StrEnum):
    """Viewer mode"""
    INTERACTIVE = 'interactive'
    FLAT = 'flat'

# -----------------------------
# Terminal input (interactive)
# -----------------------------

class Trace:
    def __init__(
            self,
            group : str,
            port : int,
            adapters : list[str] | None) -> None:
        self.group = group
        self.port = port

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", self.port))
        #self._sock.bind(("127.0.0.1", self.port))
        mreq = struct.pack("4s4s", socket.inet_aton(self.group), socket.inet_aton("127.0.0.1"))
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self._sock.setblocking(False)

        self._selector = selectors.DefaultSelector()
        self._selector.register(self._sock, selectors.EVENT_READ, data="udp")

        self._adapters = adapters

    @abstractmethod
    def run(self) -> None:
        ...

    def close(self) -> None:
        try:
            self._selector.unregister(self._sock)
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass

    def get_event(self, timeout : float | None) -> Generator[TraceEvent | None, Any, Any]:
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

class FlatTrace(Trace):
    def __init__(
            self,
            group: str = DEFAULT_MULTICAST_GROUP,
            port: int = DEFAULT_MULTICAST_PORT,
            adapters: list[str] | None = None,
            adapter_regex: str | None = None,
            time_mode: str = "rel",
            abs_time_format: str = "%H:%M:%S.%f",
            show_write_delta: bool = True,
            fragments: str = "all",
            max_preview: int = 80,
            max_events: int = 200,
            output: str | None = None) -> None:
        super().__init__(group, port, adapters)
        self.time_mode = time_mode
        self.abs_time_format = abs_time_format
        self.show_write_delta = show_write_delta
        self.fragments = fragments
        self.max_preview = max_preview
        self.max_events = max_events
        self._adapter_allow = set(adapters) if adapters else None
        self._adapter_re: re.Pattern[str] | None = re.compile(adapter_regex) if adapter_regex else None
        self._output_fh = open(output, "a", encoding="utf-8") if output else None


    def run(self) -> None:
        # No live UI; just print as events arrive.
        while True:
            for event in self.get_event(None):
                if event is not None:
                    self.print_event(event)

    def close(self) -> None:
        if self._output_fh:
            try:
                self._output_fh.flush()
                self._output_fh.close()
            except Exception:
                pass
            self._output_fh = None
        super().close()

    def _print_header(self) -> None:
        hdr = f"# syndesi-trace flat mode | host={self.group} port={self.port}"
        #hdr += f" | time={self.time_mode}"
        print(hdr)

    def print_event(self, data : TraceEvent) -> None:
        print(data)


    def _line_prefix(self, adapter: str, ts: float) -> Text:
        #st = self._get_state(adapter)
        #if st.first_seen_ts is None:
        #    st.first_seen_ts = ts

        #base = st.base_ts()
        #t_main = _format_time(ts, mode=self.time_mode, base=base, abs_fmt=self.abs_time_format)

        # Δ since last write for fragments/read
        delta = ""
        # if self.show_write_delta and kind in ("fragment", "read") and st.last_write_ts is not None:
        #     delta_s = ts - st.last_write_ts
        #     delta = f"  +{delta_s*1000:6.1f}ms"

        tag = Text()
        tag.append("time", style="dim")
        #tag.append(delta, style="dim")
        #tag.append("  ")
        tag.append(f"[{adapter}]", style=f"bold {_adapter_style(adapter)}")
        tag.append(" ")
        return tag

class InteractiveTrace(Trace):
    def __init__(
            self,
            group: str = DEFAULT_MULTICAST_GROUP,
            port: int = DEFAULT_MULTICAST_PORT,
            adapters: list[str] | None = None,
            adapter_regex: str | None = None,
            time_mode: str = "rel",
            abs_time_format: str = "%H:%M:%S.%f",
            show_write_delta: bool = True,
            fragments: str = "all",
            max_preview: int = 80,
            max_events: int = 200,
            output: str | None = None) -> None:
        super().__init__(group, port, adapters)

        if Console is None:
            print("This viewer requires 'rich'. Install it with: pip install rich", file=sys.stderr)
            raise SystemExit(2)

        self._use_stdin = os.name == "posix"
        if self._use_stdin:
            try:
                self._selector.register(sys.stdin, selectors.EVENT_READ, data="stdin")
            except Exception:
                self._use_stdin = False

        self.console = Console() if Console is not None else None
        self.adapters: dict[str, _AdapterState] = {}
        self.adapter_order: list[str] = []
        self.selected_idx: int = 0

        self.time_mode = time_mode
        self.abs_time_format = abs_time_format
        self.show_write_delta = show_write_delta
        self.fragments = fragments
        self.max_events = max_events
        self.max_preview = max_preview

        self._adapter_allow = set(adapters) if adapters else None
        self._adapter_re: re.Pattern[str] | None = re.compile(adapter_regex) if adapter_regex else None
        self._output_fh = open(output, "a", encoding="utf-8") if output else None

    def selected_adapter(self) -> str | None:
        if not self.adapter_order:
            return None
        return self.adapter_order[self.selected_idx]

    def _handle_key(self, token: str) -> bool:
        # returns False to quit
        token = token.strip()
        if token in ("q", "Q"):
            return False
        if token in ("LEFT", "h"):

            if self.adapter_order:
                self.selected_idx = (self.selected_idx - 1) % len(self.adapter_order)
        if token in ("RIGHT", "l"):
            if self.adapter_order:
                self.selected_idx = (self.selected_idx + 1) % len(self.adapter_order)
        if token in ("UP", "k"):
            if self.adapter_order:
                st = self.adapters[self.adapter_order[self.selected_idx]]
                st.auto_follow = False
                st.scroll_offset += 1
        if token in ("DOWN", "j"):
            if self.adapter_order:
                st = self.adapters[self.adapter_order[self.selected_idx]]
                if st.scroll_offset > 0:
                    st.scroll_offset -= 1
                if st.scroll_offset == 0:
                    st.auto_follow = True
        return True

    def run(self) -> None:
        with _TerminalRawMode():
            with Live(self._render_interactive(), refresh_per_second=20, screen=True) as live:
                running = True
                while running:

                    for event in self.get_event(timeout=0.05):
                        print(f'Event : {event}')
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

    def close(self) -> None:
        if self._output_fh:
            try:
                self._output_fh.flush()
                self._output_fh.close()
            except Exception:
                pass
            self._output_fh = None

    def _allow_adapter(self, name: str) -> bool:
        if self._adapter_allow is not None and name not in self._adapter_allow:
            return False
        if self._adapter_re is not None and not self._adapter_re.search(name):
            return False
        return True

    def _get_state(self, adapter: str) -> _AdapterState:
        if adapter not in self.adapters:
            self.adapters[adapter] = _AdapterState(self.max_events)
            self.adapter_order.append(adapter)
        return self.adapters[adapter]

    def _line_prefix(self, adapter: str, ts: float) -> Text:
        st = self._get_state(adapter)
        if st.first_seen_ts is None:
            st.first_seen_ts = ts

        base = st.base_ts()
        t_main = _format_time(ts, mode=self.time_mode, base=base, abs_fmt=self.abs_time_format)

        # Δ since last write for fragments/read
        delta = ""
        # if self.show_write_delta and kind in ("fragment", "read") and st.last_write_ts is not None:
        #     delta_s = ts - st.last_write_ts
        #     delta = f"  +{delta_s*1000:6.1f}ms"

        tag = Text()
        tag.append(t_main, style="dim").append(" ")
        return tag

    def _render_event_block(self, adapter: str, event : TraceEvent) -> list[Text] | None:
        """
        Returns a block of one or more Text lines.
        For "read", includes pending fragments above it (per user requirement).
        """
        st = self._get_state(adapter)
        #kind = str(d.get("kind") or d.get("type") or d.get("event") or "unknown").lower()
        ts = event.timestamp#float(d.get("timestamp") if d.get("timestamp") is not None else d.get("t", time.time()))

        #st.last_kind = kind
        st.last_ts = ts

        if st.first_seen_ts is None:
            st.first_seen_ts = ts

        if isinstance(event, OpenEvent):
            if st.open_base_ts is None:
                st.open_base_ts = ts

            prefix = self._line_prefix(adapter, ts)
            line = Text.assemble(
                prefix,
                Text("open  ●", style="bold green")
            )
            return [line]

        if isinstance(event, CloseEvent):
            prefix = self._line_prefix(adapter, ts)
            line = Text.assemble(
                prefix,
                Text("close ●", style="bold red")
            )
            return [line]

        if isinstance(event, WriteEvent):
            prefix = self._line_prefix(adapter, ts)
            line = Text.assemble(
                prefix,
                Text("write →", style="bold dim"),
                Text(f"{event.length:4d}B", style="dim"),
                Text(f" {event.data}")
            )
            return [line]

        if isinstance(event, FragmentEvent):
            prefix = self._line_prefix(adapter, ts)
            line = Text.assemble(
                prefix,
                Text("      ↓", style="dim"),
                Text(f"{event.length:4d}B ", style="dim"),
                Text(event.data, style="dim"),
                Text(" (frag)", style="dim")
            )
            return [line]

        # preview_mode = "text"  # could be extended with a CLI flag
        # if preview_mode == "text":
        #     p = _safe_text_preview(b, self.max_preview)
        # else:
        #     p = _hex_preview(b, self.max_preview)

        # ---- build blocks ----


        if isinstance(event, ReadEvent):
            prefix = self._line_prefix(adapter, ts)

            #stop = 'test'#_extract_stop_reason(d)
            #stop_badge = _badge(f"⏹ {stop}" if stop else "⏹", "bold magenta") if self.console else Text(f"⏹ {stop}".strip())

            line = Text.assemble(
                prefix,
                Text("read  ←", style="bold dim"),
                Text(f"{event.length:4d}B ", style="dim"),
                Text(f"{event.data} "),
                Text(f'({event.stop_condition_indicator})', style="dim")
            )

            return [line]



            # Render pending fragments ABOVE read (connector fixed at render time)
            # if self.fragments != "none":
            #     for i, fd in enumerate(st.pending_frags):


            #         fts = float(fd.get("timestamp") if fd.get("timestamp") is not None else fd.get("t", ts))
            #         fb, _, ftr = _extract_bytes_and_len(fd)
            #         fp = _safe_text_preview(fb, self.max_preview)
            #         connector = "├─ "  # final connector will be for READ line itself
            #         frag_lines.append(Text.assemble(
            #             self._line_prefix(adapter, fts, "fragment"),
            #             Text(f"{connector}", style="dim"),
            #             Text("🧩 FRAG", style="cyan"),
            #             Text(f"  {len(fb):4d}B", style="dim"),
            #             Text("  "),
            #             Text(fp, style="white"),
            #             Text(" …" if ftr else "", style="dim"),
            #         ))

            # Now read line (must be last; uses └─)
            #read_line.append("└─ ", style="dim")


            #read_line.append(f"  {n_total:4d}B", style="dim")

            # read_line.append("  ")
            # if self.console:
            #     read_line.append_text(stop_badge)
            # else:
            #     read_line.append(f"{stop_badge}", style="magenta")

            # read_line.append("  ")
            # read_line.append(event.data, style="white")

            # # Clear pending fragments once read completes
            # st.pending_frags.clear()
            # st.pending_bytes = 0

            # return frag_lines + [read_line]

        # Fallback
        prefix = self._line_prefix(adapter, ts)
        msg = "error" # str(d.get("message") or "")
        line = Text.assemble(prefix, Text("• kind", style="dim"), Text("  "), Text(msg, style="white"))
        return [line]

    def ingest(self, event : TraceEvent) -> bool:
        adapter_id = event.descriptor
        if not self._allow_adapter(adapter_id):
            return False

        st = self._get_state(adapter_id)

        block = self._render_event_block(adapter_id, event)
        if block:
            # If it's a fragment event and we're in interactive mode, avoid “double printing”
            # in flat mode by respecting self.fragments.
            st.blocks.append(block)
        return True

    def _emit_flat(self, block: list[Text]) -> None:
        # Flat mode: write plain text lines (no colors) for exportability
        for line in block:
            s = line.plain if hasattr(line, "plain") else str(line)
            if self._output_fh:
                self._output_fh.write(s + "\n")
            else:
                print(s)
        if self._output_fh:
            self._output_fh.flush()

    def _render_tabs(self) -> Text:
        names = self.adapter_order[:] or ["(no adapters)"]
        t = Text()
        t.append("Adapters: ", style="dim")
        for i, name in enumerate(names):
            sel = (i == self.selected_idx)
            style = f"bold reverse {_adapter_style(name)}" if sel else f"{_adapter_style(name)}"
            t.append(f" {name} ", style=style)
        t.append("   ", style="dim")
        t.append("←/→ switch  ↑/↓ scroll  q quit  (h/j/k/l also)", style="dim")
        return t

    def _render_interactive(self) -> Panel:
        if not self.adapter_order:
            body = Text("Waiting for events…", style="dim")
            return Panel(Align.left(body), title="Syndesi Trace", border_style="dim")

        selected = self.adapter_order[self.selected_idx]
        st = self.adapters[selected]

        # Compose recent blocks into lines
        lines: list[Text] = []
        for block in st.blocks:
            lines.extend(block)

        # Add “read in progress” hint (best-effort)
        # if st.pending_frags:
        #     # show a pinned in-progress line at the bottom
        #     last_ts = st.last_ts or st.first_seen_ts or time.time()
        #     prefix = self._line_prefix(selected, float(last_ts), "read")
        #     inprog = Text.assemble(
        #         prefix,
        #         Text("⏳ reading…", style="yellow"),
        #         Text(f"  frags={len(st.pending_frags)}", style="dim"),
        #         Text(f"  bytes≈{st.pending_bytes}", style="dim"),
        #     )
        #     lines.append(Text(""))
        #     lines.append(inprog)

        if not lines:
            lines = [Text("No events yet for this adapter.", style="dim")]

        body = Text("\n").join(self._visible_lines(lines, st))
        header = self._render_tabs()

        # Wrap body in a panel; header goes as title-ish via subtitle
        return Panel(
            Align.left(body),
            title=header,
            border_style="bright_black",
            padding=(1, 1),
        )

    def _visible_lines(self, lines: list[Text], st: _AdapterState) -> list[Text]:
        height = self.console.size.height if self.console is not None else 24
        # Reserve space for borders, title, and padding.
        visible = max(1, height - 6)
        total = len(lines)
        max_offset = max(0, total - visible)
        if st.auto_follow:
            st.scroll_offset = 0
        else:
            st.scroll_offset = min(max_offset, st.scroll_offset)
        start = max(0, total - visible - st.scroll_offset)
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
            import termios
            import tty
            fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(fd)
            tty.setcbreak(fd)
            self._enabled = True
        except Exception:
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
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old)
        except Exception:
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
    except Exception:
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
# Rendering helpers
# -----------------------------

# def _is_probably_epoch(ts: float) -> bool:
#     # heuristic: epoch seconds are ~ 1.6e9+; perf_counter is usually much smaller
#     return ts > 1_500_000_000

def _format_time(ts: float, *, mode: str, base: float | None, abs_fmt: str) -> str:
    if mode == "abs":
        # if _is_probably_epoch(ts):
        #     dt = _dt.datetime.fromtimestamp(ts)
        #     return dt.strftime(abs_fmt)
        # fallback: monotonic "T+..."
        if base is None:
            base = ts
        return f"T+{(ts - base):8.3f}s"
    # relative
    if base is None:
        base = ts
    return f"{(ts - base):8.3f}s"


def _safe_text_preview(b: bytes, limit: int) -> str:
    if not b:
        return ""
    s = b.decode("utf-8", "replace").replace("\r", "\\r").replace("\n", "\\n")
    if len(s) > limit:
        s = s[:limit] + "…"
    return s


# def _hex_preview(b: bytes, limit: int) -> str:
#     if not b:
#         return ""
#     s = b.hex()
#     if len(s) > limit:
#         s = s[:limit] + "…"
#     return s

#     if isinstance(d.get("data"), str):
#         # treat as preview only
#         return d["data"].encode("utf-8", "replace"), total_len, truncated

#     if isinstance(d.get("data_b64"), str) and d["data_b64"]:
#         try:
#             b = base64.b64decode(d["data_b64"].encode("ascii"), validate=False)
#             return b, total_len, truncated
#         except Exception:
#             return b"", total_len, True

#     if isinstance(d.get("data_hex"), str) and d["data_hex"]:
#         try:
#             b = bytes.fromhex(d["data_hex"])
#             return b, total_len, truncated
#         except Exception:
#             return b"", total_len, True

#     return b"", total_len, truncated

def _adapter_style(name: str) -> str:
    # stable-ish per adapter
    colors = ["cyan", "magenta", "green", "yellow", "blue", "bright_cyan", "bright_magenta", "bright_green"]
    idx = abs(hash(name)) % len(colors)
    return colors[idx]

# -----------------------------
# Viewer state
# -----------------------------

class _AdapterState:
    def __init__(self, max_events: int) -> None:
        self.open_base_ts: float | None = None
        self.first_seen_ts: float | None = None
        self.last_write_ts: float | None = None

        # "pending fragments" before next read completion
        self.pending_frags: list[dict[str, Any]] = []
        self.pending_bytes: int = 0

        # rolling rendered blocks for display (each block is list[Text])
        maxlen = max_events if max_events > 0 else None
        self.blocks: deque[list[Text]] = deque(maxlen=maxlen)

        # last activity
        self.last_kind: str = ""
        self.last_ts: float | None = None

        # interactive scroll state
        self.scroll_offset: int = 0
        self.auto_follow: bool = True

    def base_ts(self) -> float | None:
        return self.open_base_ts or self.first_seen_ts

# -----------------------------
# Main loop
# -----------------------------

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="syndesi-trace", description="Live console viewer for Syndesi trace events (UDP).")

    parser.add_argument(
        "--mode",
        choices=[str(x) for x in TraceMode],
        default=TraceMode.INTERACTIVE.value,
        help="Display mode. interactive: tabs per adapter. flat: append-only timeline.",
    )

    # parser.add_argument(
    #     "--view",
    #     choices=["timeline"],
    #     default="timeline",
    #     help="Reserved for future (kept for CLI stability).",
    # )

    # Network
    #parser.add_argument("--listen-host", default=DEFAULT_MULTICAST_GROUP, help="Host/interface to bind (default: 127.0.0.1).")
    parser.add_argument("--listen-port", type=int, default=DEFAULT_MULTICAST_PORT, help="UDP port to bind (default: 12000).")
    parser.add_argument(
        "--multicast-group",
        default=DEFAULT_MULTICAST_GROUP,
        help="If set, join this UDP multicast group (enables true pub/sub without producer client management).",
    )

    # Filtering
    parser.add_argument("--adapter", action="append", default=[], help="Show only this adapter (repeatable).")
    parser.add_argument("--adapter-regex", default=None, help="Regex filter on adapter name.")

    # Time
    parser.add_argument("--time", dest="time_mode", choices=["rel", "abs"], default="rel",
                        help="Time display: rel = relative to adapter open/first seen, abs = wall time if timestamp looks like epoch.")
    parser.add_argument("--abs-time-format", default="%H:%M:%S.%f",
                        help="strftime format for --time abs (default: %%H:%%M:%%S.%%f).")
    parser.add_argument("--no-write-delta", dest="show_write_delta", action="store_false",
                        help="Disable the extra +Δt shown for fragments/reads relative to the last TX/write.")
    parser.set_defaults(show_write_delta=True)

    # Content verbosity
    parser.add_argument("--fragments", choices=["auto", "all", "none"], default="all",
                        help="Fragment visibility. all=show fragments. none=hide fragments. auto reserved for future.")
    parser.add_argument("--max-preview", type=int, default=80, help="Max preview chars for payload display.")
    parser.add_argument("--max-events", type=int, default=200, help="Max event blocks kept per adapter in interactive mode (0 = unlimited).")

    # Output (flat)
    parser.add_argument("--output", default=None, help="Write flat output to this file instead of stdout.")

    args = parser.parse_args(argv)

    mode = TraceMode(args.mode)

    trace : Trace

    if mode == TraceMode.INTERACTIVE:
        trace = InteractiveTrace(
            group=args.multicast_group,
            port=args.listen_port,
            adapters=args.adapter or None,
            adapter_regex=args.adapter_regex,
            time_mode=args.time_mode,
            abs_time_format=args.abs_time_format,
            show_write_delta=args.show_write_delta,
            fragments=args.fragments,
            max_preview=args.max_preview,
            max_events=args.max_events,
            output=args.output,
        )
    elif mode == TraceMode.FLAT:
        trace = FlatTrace(
            group=args.multicast_group,
            port=args.listen_port,
            adapters=args.adapter or None,
            adapter_regex=args.adapter_regex,
            time_mode=args.time_mode,
            abs_time_format=args.abs_time_format,
            show_write_delta=args.show_write_delta,
            fragments=args.fragments,
            max_preview=args.max_preview,
            max_events=args.max_events,
            output=args.output,
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
