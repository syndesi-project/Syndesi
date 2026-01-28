# File : syndesi_trace.py
# Author : Sébastien Deriaz
# License : GPL

from __future__ import annotations
from enum import StrEnum

# import json
# import socket
# import struct

from syndesi.adapters.tracehub import (
    DEFAULT_MULTICAST_GROUP,
    DEFAULT_MULTICAST_PORT,
    json_to_trace_event
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
import base64
import datetime as _dt
import json
import os
import re
import selectors
import socket
import struct
import sys
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Optional, Tuple

try:
    from rich.align import Align
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text
except Exception:  # pragma: no cover
    Console = None  # type: ignore


class ViewerMode(StrEnum):
    """Viewer mode"""
    INTERACTIVE = 'interactive'
    FLAT = 'flat'

# -----------------------------
# Terminal input (interactive)
# -----------------------------

class _TerminalRawMode:
    """Best-effort cbreak/raw mode (POSIX). Windows falls back to polling msvcrt."""
    def __init__(self) -> None:
        self._enabled = False
        self._old = None

    def __enter__(self):
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

    def __exit__(self, exc_type, exc, tb):
        if os.name != "posix":
            return
        if not self._enabled or self._old is None:
            return
        try:
            import termios
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old)
        except Exception:
            pass


def _read_keys_nonblocking() -> List[str]:
    """
    Read available keys without blocking.
    Returns a list of key tokens: "LEFT", "RIGHT", "q", etc.
    """
    keys: List[str] = []

    if os.name == "nt":
        try:
            import msvcrt
            while msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):  # special key prefix
                    ch2 = msvcrt.getwch()
                    if ch2 == "K":
                        keys.append("LEFT")
                    elif ch2 == "M":
                        keys.append("RIGHT")
                else:
                    keys.append(ch)
        except Exception:
            return keys
        return keys

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
            i += 1
            continue
        keys.append(ch)
        i += 1

    return keys


# -----------------------------
# Rendering helpers
# -----------------------------

def _is_probably_epoch(ts: float) -> bool:
    # heuristic: epoch seconds are ~ 1.6e9+; perf_counter is usually much smaller
    return ts > 1_500_000_000


def _format_time(ts: float, *, mode: str, base: Optional[float], abs_fmt: str) -> str:
    if mode == "abs":
        if _is_probably_epoch(ts):
            dt = _dt.datetime.fromtimestamp(ts)
            return dt.strftime(abs_fmt)
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


def _hex_preview(b: bytes, limit: int) -> str:
    if not b:
        return ""
    s = b.hex()
    if len(s) > limit:
        s = s[:limit] + "…"
    return s


def _extract_bytes_and_len(d: dict[str, Any]) -> Tuple[bytes, Optional[int], bool]:
    """
    Returns (bytes_preview, total_len, truncated?)
    - If 'data' is present as str, we treat it as preview and do not decode to bytes.
    """
    total_len: Optional[int] = None
    truncated = bool(d.get("data_trunc") or d.get("truncated"))
    for k in ("data_len", "nbytes", "length"):
        if isinstance(d.get(k), int):
            total_len = int(d[k])
            break

    if isinstance(d.get("data"), str):
        # treat as preview only
        return d["data"].encode("utf-8", "replace"), total_len, truncated

    if isinstance(d.get("data_b64"), str) and d["data_b64"]:
        try:
            b = base64.b64decode(d["data_b64"].encode("ascii"), validate=False)
            return b, total_len, truncated
        except Exception:
            return b"", total_len, True

    if isinstance(d.get("data_hex"), str) and d["data_hex"]:
        try:
            b = bytes.fromhex(d["data_hex"])
            return b, total_len, truncated
        except Exception:
            return b"", total_len, True

    return b"", total_len, truncated


def _extract_stop_reason(d: dict[str, Any]) -> str:
    v = d.get("stop_reason") or d.get("stop_condition") or d.get("stop")
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        # common shapes: {"kind":"DELIM","value":"\\n"} etc.
        kind = v.get("kind") or v.get("type") or v.get("name")
        val = v.get("value") or v.get("param") or v.get("delimiter")
        if kind and val is not None:
            return f"{kind} {val!r}"
        if kind:
            return str(kind)
    return str(v)


def _adapter_style(name: str) -> str:
    # stable-ish per adapter
    colors = ["cyan", "magenta", "green", "yellow", "blue", "bright_cyan", "bright_magenta", "bright_green"]
    idx = abs(hash(name)) % len(colors)
    return colors[idx]


def _badge(text: str, style: str) -> Text:
    t = Text(f" {text} ", style=style)
    return t


# -----------------------------
# Viewer state
# -----------------------------


class _AdapterState:
    def __init__(self, max_events: int) -> None:
        self.open_base_ts: Optional[float] = None
        self.first_seen_ts: Optional[float] = None
        self.last_write_ts: Optional[float] = None

        # "pending fragments" before next read completion
        self.pending_frags: List[dict[str, Any]] = []
        self.pending_bytes: int = 0

        # rolling rendered blocks for display (each block is list[Text])
        self.blocks: Deque[List[Text]] = deque(maxlen=max_events)

        # last activity
        self.last_kind: str = ""
        self.last_ts: Optional[float] = None

    def base_ts(self) -> Optional[float]:
        return self.open_base_ts or self.first_seen_ts


class _Viewer:
    def __init__(self) -> None:
        self.console = Console() if Console is not None else None
        self.adapters: Dict[str, _AdapterState] = {}
        self.adapter_order: List[str] = []
        self.selected_idx: int = 0

        self._adapter_allow: Optional[set[str]] = set(args.adapter) if args.adapter else None
        self._adapter_re: Optional[re.Pattern[str]] = re.compile(args.adapter_regex) if args.adapter_regex else None

        self._output_fh = open(args.output, "a", encoding="utf-8") if args.output else None

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
            self.adapters[adapter] = _AdapterState(self.args.max_events)
            self.adapter_order.append(adapter)
        return self.adapters[adapter]

    def _line_prefix(self, adapter: str, ts: float, kind: str) -> Text:
        st = self._get_state(adapter)
        if st.first_seen_ts is None:
            st.first_seen_ts = ts

        base = st.base_ts()
        t_main = _format_time(ts, mode=self.args.time_mode, base=base, abs_fmt=self.args.abs_time_format)

        # Δ since last write for fragments/read
        delta = ""
        if self.args.show_write_delta and kind in ("fragment", "read") and st.last_write_ts is not None:
            delta_s = ts - st.last_write_ts
            delta = f"  +{delta_s*1000:6.1f}ms"

        tag = Text()
        tag.append(t_main, style="dim")
        tag.append(delta, style="dim")
        tag.append("  ")
        tag.append(f"[{adapter}]", style=f"bold {_adapter_style(adapter)}")
        tag.append(" ")
        return tag

    def _render_event_block(self, adapter: str, d: dict[str, Any]) -> Optional[List[Text]]:
        """
        Returns a block of one or more Text lines.
        For "read", includes pending fragments above it (per user requirement).
        """
        st = self._get_state(adapter)
        kind = str(d.get("kind") or d.get("type") or d.get("event") or "unknown").lower()
        ts = float(d.get("timestamp") if d.get("timestamp") is not None else d.get("t", time.time()))

        st.last_kind = kind
        st.last_ts = ts

        # Track open base time
        if kind == "open" and st.open_base_ts is None:
            st.open_base_ts = ts
        if st.first_seen_ts is None:
            st.first_seen_ts = ts

        # Interpret "write" / "tx" as "previous write"
        if kind in ("tx", "write") or str(d.get("direction", "")).upper() == "TX":
            st.last_write_ts = ts

        # Extract payload preview
        b, total_len, truncated = _extract_bytes_and_len(d)
        n_preview = len(b)
        n_total = total_len if total_len is not None else (int(d.get("n")) if isinstance(d.get("n"), int) else None)

        preview_mode = "text"  # could be extended with a CLI flag
        if preview_mode == "text":
            p = _safe_text_preview(b, self.args.max_preview)
        else:
            p = _hex_preview(b, self.args.max_preview)

        # ---- build blocks ----

        if kind == "fragment":
            # store pending; also add a "live line" block if showing fragments
            st.pending_frags.append(d)
            st.pending_bytes += (n_total if n_total is not None else n_preview)

            if self.args.fragments == "none":
                return None

            prefix = self._line_prefix(adapter, ts, kind)
            line = Text.assemble(
                prefix,
                Text("├─ ", style="dim"),
                Text("🧩 FRAG", style="cyan"),
                Text(f"  {n_preview:4d}B", style="dim"),
                Text("  "),
                Text(p, style="white"),
                Text(" …" if truncated else "", style="dim"),
            )
            return [line]

        if kind == "read":
            prefix = self._line_prefix(adapter, ts, kind)
            stop = _extract_stop_reason(d)
            stop_badge = _badge(f"⏹ {stop}" if stop else "⏹", "bold magenta") if self.console else Text(f"⏹ {stop}".strip())

            # Render pending fragments ABOVE read (connector fixed at render time)
            frag_lines: List[Text] = []
            if self.args.fragments != "none":
                for i, fd in enumerate(st.pending_frags):
                    fts = float(fd.get("timestamp") if fd.get("timestamp") is not None else fd.get("t", ts))
                    fb, _, ftr = _extract_bytes_and_len(fd)
                    fp = _safe_text_preview(fb, self.args.max_preview)
                    connector = "├─ "  # final connector will be for READ line itself
                    frag_lines.append(Text.assemble(
                        self._line_prefix(adapter, fts, "fragment"),
                        Text(f"{connector}", style="dim"),
                        Text("🧩 FRAG", style="cyan"),
                        Text(f"  {len(fb):4d}B", style="dim"),
                        Text("  "),
                        Text(fp, style="white"),
                        Text(" …" if ftr else "", style="dim"),
                    ))

            # Now read line (must be last; uses └─)
            read_line = Text()
            read_line.append_text(prefix)
            read_line.append("└─ ", style="dim")
            read_line.append("🧵 READ", style="bold bright_white")

            # byte count
            if n_total is None:
                # if producer doesn't send total len, approximate with preview
                n_total = n_preview
            read_line.append(f"  {n_total:4d}B", style="dim")

            read_line.append("  ")
            if self.console:
                read_line.append_text(stop_badge)
            else:
                read_line.append(f"{stop_badge}", style="magenta")

            read_line.append("  ")
            read_line.append(p, style="white")
            if truncated:
                read_line.append(" …", style="dim")

            # Clear pending fragments once read completes
            st.pending_frags.clear()
            st.pending_bytes = 0

            return frag_lines + [read_line]

        if kind == "open":
            prefix = self._line_prefix(adapter, ts, kind)
            msg = str(d.get("message") or d.get("url") or d.get("resource") or "")
            line = Text.assemble(prefix, Text("🔌✅ OPEN", style="bold green"), Text("  "), Text(msg, style="white"))
            return [line]

        if kind == "close":
            prefix = self._line_prefix(adapter, ts, kind)
            msg = str(d.get("message") or "")
            line = Text.assemble(prefix, Text("🔌🛑 CLOSE", style="bold red"), Text("  "), Text(msg, style="white"))
            return [line]

        if kind in ("tx", "write"):
            prefix = self._line_prefix(adapter, ts, kind)
            line = Text.assemble(prefix, Text("📤 TX", style="green"), Text(f"  {n_preview:4d}B", style="dim"),
                                 Text("  "), Text(p, style="white"), Text(" …" if truncated else "", style="dim"))
            return [line]

        if kind in ("error", "exception"):
            prefix = self._line_prefix(adapter, ts, kind)
            msg = str(d.get("message") or d.get("error") or "")
            line = Text.assemble(prefix, Text("❌ ERROR", style="bold red"), Text("  "), Text(msg, style="white"))
            return [line]

        # Fallback
        prefix = self._line_prefix(adapter, ts, kind)
        msg = str(d.get("message") or "")
        line = Text.assemble(prefix, Text(f"• {kind.upper()}", style="dim"), Text("  "), Text(msg, style="white"))
        return [line]

    def ingest(self, d: dict[str, Any]) -> bool:
        adapter = str(d.get("adapter") or d.get("adapter_id") or d.get("port") or "default")
        if not self._allow_adapter(adapter):
            return False

        st = self._get_state(adapter)

        block = self._render_event_block(adapter, d)
        if block:
            # If it's a fragment event and we're in interactive mode, avoid “double printing”
            # in flat mode by respecting args.fragments.
            st.blocks.append(block)
            if self.args.mode == "flat":
                self._emit_flat(block)
        return True

    def _emit_flat(self, block: List[Text]) -> None:
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
        t.append("←/→ switch  q quit  (h/l also)", style="dim")
        return t

    def _render_interactive(self) -> Panel:
        if not self.adapter_order:
            body = Text("Waiting for events…", style="dim")
            return Panel(Align.left(body), title="Syndesi Trace", border_style="dim")

        selected = self.adapter_order[self.selected_idx]
        st = self.adapters[selected]

        # Compose recent blocks into lines
        lines: List[Text] = []
        for block in st.blocks:
            lines.extend(block)

        # Add “read in progress” hint (best-effort)
        if st.pending_frags:
            # show a pinned in-progress line at the bottom
            last_ts = st.last_ts or st.first_seen_ts or time.time()
            prefix = self._line_prefix(selected, float(last_ts), "read")
            inprog = Text.assemble(
                prefix,
                Text("⏳ reading…", style="yellow"),
                Text(f"  frags={len(st.pending_frags)}", style="dim"),
                Text(f"  bytes≈{st.pending_bytes}", style="dim"),
            )
            lines.append(Text(""))
            lines.append(inprog)

        if not lines:
            lines = [Text("No events yet for this adapter.", style="dim")]

        body = Text("\n").join(lines)
        header = self._render_tabs()

        # Wrap body in a panel; header goes as title-ish via subtitle
        return Panel(
            Align.left(body),
            title=header,
            border_style="bright_black",
            padding=(1, 1),
        )

    def _render_flat_header(self) -> None:
        if self.args.mode != "flat":
            return
        hdr = f"# syndesi-trace flat mode | host={self.args.listen_host} port={self.args.listen_port}"
        if self.args.multicast_group:
            hdr += f" mcast={self.args.multicast_group}"
        hdr += f" | time={self.args.time_mode}"
        print(hdr)

    def selected_adapter(self) -> Optional[str]:
        if not self.adapter_order:
            return None
        return self.adapter_order[self.selected_idx]

class Display:
    def __init__(self, multicast_group : str, port : int) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("localhost", port))
        mreq = struct.pack("4s4s", socket.inet_aton(multicast_group), socket.inet_aton("0.0.0.0"))
        self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self._sock.setblocking(False)

        self._selector = selectors.DefaultSelector()
        self._selector.register(self._sock, selectors.EVENT_READ, data="udp")

    def run(self, mode : ViewerMode):
        try:
            if mode == ViewerMode.INTERACTIVE:
                self.run_interactive_mode()
            elif mode == ViewerMode.FLAT:
                self.run_flat_mode()
        except KeyboardInterrupt:
            pass
        finally:
            #viewer.close()
            try:
                self._selector.unregister(self._sock)
            except Exception:
                pass
            try:
                self._sock.close()
            except Exception:
                pass

    def run_flat_mode(self):
        # No live UI; just print as events arrive.
        while True:
            events = self._selector.select(timeout=0.5)
            for key, _ in events:
                if key.data == "udp":
                    while True:
                        try:
                            data, _addr = sock.recvfrom(65535)
                            print(f'Data : {data}')
                        except BlockingIOError:
                            break
                        try:
                            d = json.loads(data.decode("utf-8", "replace"))
                            if isinstance(d, dict):
                                viewer.ingest(d)
                        except Exception:
                            # ignore malformed packet
                            continue

    def run_interactive_mode(self):
        # Interactive: alternate screen, render tabs + selected adapter panel.
        with _TerminalRawMode():
            with Live(viewer._render_interactive(), refresh_per_second=20, screen=True) as live:
                running = True
                while running:
                    events = sel.select(timeout=0.1)

                    # Windows key polling (no selector on stdin)
                    if os.name == "nt":
                        for k in _read_keys_nonblocking():
                            running = handle_key(k)
                            if not running:
                                break

                    for key, _ in events:
                        if key.data == "udp":
                            # Drain all available datagrams
                            while True:
                                try:
                                    data, _addr = sock.recvfrom(65535)
                                    print(f'Data : {data}')
                                except BlockingIOError:
                                    break
                                try:
                                    d = json.loads(data.decode("utf-8", "replace"))
                                    if isinstance(d, dict):
                                        viewer.ingest(d)
                                except Exception:
                                    continue

                        elif key.data == "stdin":
                            for k in _read_keys_nonblocking():
                                running = handle_key(k)
                                if not running:
                                    break

                    live.update(viewer._render_interactive())
                    if not running:
                        break

# -----------------------------
# Main loop
# -----------------------------

def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="syndesi-trace", description="Live console viewer for Syndesi trace events (UDP).")

    parser.add_argument(
        "--mode",
        choices=[str(x) for x in ViewerMode],
        default=ViewerMode.INTERACTIVE.value,
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
    parser.add_argument("--max-events", type=int, default=200, help="Max event blocks kept per adapter in interactive mode.")

    # Output (flat)
    parser.add_argument("--output", default=None, help="Write flat output to this file instead of stdout.")

    args = parser.parse_args(argv)

    mode = ViewerMode(args.mode)

    if Console is None:
        print("This viewer requires 'rich'. Install it with: pip install rich", file=sys.stderr)
        raise SystemExit(2)

    viewer = _Viewer(args)
    print(f'Make UDP socket : {args.listen_host}:{args.listen_port}')

    use_stdin = (args.mode == "interactive" and os.name == "posix")
    if use_stdin:
        try:
            sel.register(sys.stdin, selectors.EVENT_READ, data="stdin")
        except Exception:
            use_stdin = False

    viewer._render_flat_header()

    def handle_key(token: str) -> bool:
        # returns False to quit
        token = token.strip()
        if token in ("q", "Q"):
            return False
        if token in ("LEFT", "h"):
            if viewer.adapter_order:
                viewer.selected_idx = (viewer.selected_idx - 1) % len(viewer.adapter_order)
        if token in ("RIGHT", "l"):
            if viewer.adapter_order:
                viewer.selected_idx = (viewer.selected_idx + 1) % len(viewer.adapter_order)
        return True

    trace = Display()

    trace.run(mode)


if __name__ == "__main__":
    main()
