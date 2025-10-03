# File : visa.py
# Author : Sébastien Deriaz
# License : GPL
#
# The VISA backend communicates using pyvisa

from __future__ import annotations

import queue
import socket
import threading
import time
from types import ModuleType
from typing import TYPE_CHECKING

from ...tools.backend_api import AdapterBackendStatus, Fragment
from .adapter_backend import (
    AdapterBackend,
    AdapterDisconnected,
    AdapterSignal,
    HasFileno,
)
from .descriptors import VisaDescriptor

# --- Typing-only imports so mypy knows pyvisa symbols without requiring it at runtime
if TYPE_CHECKING:
    import pyvisa  # type: ignore
    from pyvisa.resources import Resource  # type: ignore

# --- Runtime optional import
try:
    import pyvisa as _pyvisa_runtime
except Exception:
    _pyvisa_runtime = None

pyvisa: ModuleType | None = _pyvisa_runtime  # type: ignore


class VisaBackend(AdapterBackend):
    def __init__(self, descriptor: VisaDescriptor):
        """
        USB VISA stack adapter
        """
        super().__init__(descriptor=descriptor)
        self.descriptor: VisaDescriptor

        if pyvisa is None:
            raise ImportError(
                "Missing optional dependency 'pyvisa'. Install with:\n"
                "  python -m pip install pyvisa"
            )

        # Safe: guarded above, so mypy knows pyvisa is a module here
        self._rm = pyvisa.ResourceManager()
        self._inst: Resource | None = None  # annotation only; no runtime import needed

        # We need a socket pair because VISA doesn't expose a selectable fileno/socket
        # So we create a thread to read data and push that to the socket
        self._notify_recv, self._notify_send = socket.socketpair()
        self._notify_recv.setblocking(False)
        self._notify_send.setblocking(False)

        self._stop_lock = threading.Lock()
        self.stop = False

        self._fragment_lock = threading.Lock()
        self._fragment = Fragment(b"", None)
        self._event_queue: queue.Queue[AdapterSignal] = queue.Queue()

    @classmethod
    def list_devices(cls: type[VisaBackend]) -> list[str]:
        """
        Returns a list of available VISA devices
        """
        if pyvisa is None:
            raise ImportError(
                "Missing optional dependency 'pyvisa'. Install with:\n"
                "  python -m pip install pyvisa"
            )

        rm = pyvisa.ResourceManager()
        available_resources: list[str] = []
        for device in rm.list_resources():
            try:
                d = rm.open_resource(device)
                d.close()
                available_resources.append(device)
            except pyvisa.VisaIOError:
                # Device cannot be opened; skip it
                pass

        return available_resources

    def flush_read(self) -> bool:
        super().flush_read()
        while not self._event_queue.empty():
            self._event_queue.get()
        return True

    def open(self) -> bool:
        output = False
        if self._inst is None:
            # NOTE: self._rm is always defined in __init__ when pyvisa is present
            self._inst = self._rm.open_resource(self.descriptor.descriptor)

        if self._status == AdapterBackendStatus.DISCONNECTED:
            # These attributes exist on pyvisa resources
            self._inst.write_termination = ""
            self._inst.read_termination = None

            self._inst_lock = threading.Lock()
            self._status = AdapterBackendStatus.CONNECTED

        if self._thread is None:
            self._thread = threading.Thread(
                target=self._internal_thread,
                args=(self._inst, self._event_queue),
                daemon=True,
            )
            self._thread.start()
            output = True

        return output

    def close(self) -> bool:
        super().close()
        with self._inst_lock:
            if self._inst is not None:
                self._inst.close()
        self._status = AdapterBackendStatus.DISCONNECTED
        with self._stop_lock:
            self.stop = True
        return True

    def write(self, data: bytes) -> bool:
        super().write(data)
        with self._inst_lock:
            if self._inst is not None:
                self._inst.write_raw(data)
        return True

    def _socket_read(self) -> Fragment:
        self._notify_recv.recv(1)
        if not self._event_queue.empty():
            event = self._event_queue.get()
            if isinstance(event, AdapterDisconnected):
                return Fragment(b"", None)

        with self._fragment_lock:
            output = self._fragment
            self._fragment = Fragment(b"", None)
            return output

    def _internal_thread(
        self,
        inst: Resource,
        event_queue: queue.Queue[AdapterSignal],
    ) -> None:
        assert pyvisa is not None  # for type-narrowing inside this method
        timeout = 2000
        while True:
            payload = b""
            with self._fragment_lock:
                self._fragment = Fragment(b"", None)
            try:
                inst.timeout = timeout
            except pyvisa.InvalidSession:
                pass
            try:
                while True:
                    # Read up to an error
                    payload += inst.read_bytes(1)
                    inst.timeout = 0
            except pyvisa.VisaIOError:
                # Timeout
                if payload:
                    with self._fragment_lock:
                        if self._fragment.timestamp is None:
                            self._fragment.timestamp = time.time()
                            self._fragment.data += payload
                    # Tell the session that there's data (write to a virtual socket)
                    self._notify_send.send(b"1")
            except (TypeError, pyvisa.InvalidSession, BrokenPipeError):
                event_queue.put(AdapterDisconnected())
                self._notify_send.send(b"1")
            with self._stop_lock:
                if self.stop:
                    break

    def selectable(self) -> HasFileno | None:
        return self._notify_recv

    def is_opened(self) -> bool:
        if self._inst is None:
            return False
        else:
            return self._status == AdapterBackendStatus.CONNECTED
