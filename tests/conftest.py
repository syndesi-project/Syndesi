"""
Fixtures shared by every test directory
"""

import os
import queue
from collections.abc import Callable

import pytest

# ┌──────────────┐
# │ Fake hidapi  │
# └──────────────┘


class FakeHIDHardware:
    """
    A HID device on the fake USB bus

    on_write(report) receives each output report (report id included) and returns the
    input reports to answer with. answer() queues an input report at any time
    """

    def __init__(
        self,
        vendor_id: int,
        product_id: int,
        *,
        serial_number: str = "",
        interface: int = 0,
        product: str = "Fake HID",
        on_write: Callable[[bytes], list[bytes]] | None = None,
    ) -> None:
        self.vendor_id = vendor_id
        self.product_id = product_id
        self.serial_number = serial_number
        self.interface = interface
        self.product = product
        self.path = f"fake-hid-{vendor_id:04x}-{product_id:04x}-{interface}-{serial_number}"
        self.on_write = on_write
        self.inputs: queue.Queue[bytes] = queue.Queue()
        self.written: list[bytes] = []
        self.features: dict[int, bytes] = {}
        self.sent_features: list[bytes] = []
        self.unplugged = False
        self.opened = 0

    def answer(self, report: bytes) -> None:
        self.inputs.put(report)

    def info(self) -> dict[str, object]:
        return {
            "path": os.fsencode(self.path),
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "serial_number": self.serial_number,
            "release_number": 0x0100,
            "manufacturer_string": "Syndesi",
            "product_string": self.product,
            "usage_page": 0xFF00,
            "usage": 1,
            "interface_number": self.interface,
        }


class FakeHIDHandle:
    """hid.device of cython-hidapi, on the fake bus"""

    def __init__(self, bus: "FakeHidapi") -> None:
        self._bus = bus
        self._hardware: FakeHIDHardware | None = None

    def open_path(self, path: bytes) -> None:
        for hardware in self._bus.hardware:
            if os.fsencode(hardware.path) == path and not hardware.unplugged:
                self._hardware = hardware
                hardware.opened += 1
                return
        raise OSError("open failed")

    def close(self) -> None:
        self._hardware = None

    def _device(self) -> FakeHIDHardware:
        if self._hardware is None:
            raise ValueError("not open")
        if self._hardware.unplugged:
            raise OSError("read error")
        return self._hardware

    def read(self, max_length: int, timeout_ms: int = 0) -> list[int]:
        hardware = self._device()
        try:
            report = hardware.inputs.get(timeout=timeout_ms / 1000 if timeout_ms else None)
        except queue.Empty:
            return []
        return list(report[:max_length])

    def write(self, buff: bytes) -> int:
        hardware = self._device()
        report = bytes(buff)
        hardware.written.append(report)
        if hardware.on_write is not None:
            for answer in hardware.on_write(report):
                hardware.answer(answer)
        return len(report)

    def get_feature_report(self, report_num: int, max_length: int) -> list[int]:
        hardware = self._device()
        return list((bytes([report_num]) + hardware.features.get(report_num, b""))[:max_length])

    def send_feature_report(self, buff: bytes) -> int:
        hardware = self._device()
        hardware.sent_features.append(bytes(buff))
        return len(buff)

    def error(self) -> str:
        return "fake error"


class FakeHidapi:
    """Stands for the hid module of cython-hidapi"""

    Hardware = FakeHIDHardware

    def __init__(self) -> None:
        self.hardware: list[FakeHIDHardware] = []

    def plug(self, hardware: FakeHIDHardware) -> FakeHIDHardware:
        self.hardware.append(hardware)
        return hardware

    def enumerate(self, vendor_id: int = 0, product_id: int = 0) -> list[dict[str, object]]:
        return [
            h.info()
            for h in self.hardware
            if not h.unplugged
            and (vendor_id == 0 or h.vendor_id == vendor_id)
            and (product_id == 0 or h.product_id == product_id)
        ]

    def device(self) -> FakeHIDHandle:
        return FakeHIDHandle(self)


@pytest.fixture
def fake_hidapi(monkeypatch: pytest.MonkeyPatch) -> FakeHidapi:
    """Replace hidapi with an empty fake USB bus, plug devices with .plug()"""
    from syndesi.adapters import hid  # pylint: disable=import-outside-toplevel

    fake = FakeHidapi()
    monkeypatch.setattr(hid, "_hidapi", fake)
    return fake
