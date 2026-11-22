"""
HID adapter, on a fake hidapi (see tests/conftest.py)

Real hardware is needed to test it end to end
"""

import asyncio
import time

import pytest

from syndesi import HID, AsyncHID, Termination, auto_adapter, auto_async_adapter
from syndesi.adapters import hid as hid_module
from syndesi.adapters.events import AdapterClosedEvent
from syndesi.adapters.hid import HIDDescriptor
from syndesi.tools.errors import (
    AdapterConfigurationError,
    AdapterDisconnectedError,
    AdapterOpenError,
    AdapterWriteError,
)


def echo(report: bytes) -> list[bytes]:
    """Answer each report with its content, without the report id"""
    return [report[1:]]


# ┌─────────────┐
# │ Descriptors │
# └─────────────┘


@pytest.mark.parametrize(
    "string",
    [
        "hid:04d8:00dd",
        "hid:04d8:00dd:SN0042",
        "hid:04d8:00dd@2",
        "hid:04d8:00dd:SN0042@2",
        "hid:path=/dev/hidraw3",
        "hid:path=1-2:1.2",
    ],
)
def test_descriptor_round_trip(string):
    assert str(HIDDescriptor.from_string(string)) == string


def test_descriptor_ids_are_hexadecimal():
    descriptor = HIDDescriptor.from_string("hid:04D8:00DD")
    assert (descriptor.vendor_id, descriptor.product_id) == (0x04D8, 0x00DD)
    assert str(descriptor) == "hid:04d8:00dd"


@pytest.mark.parametrize("string", ["hid:4d8:dd", "hid:04d8", "hid:path=", "hid:"])
def test_invalid_descriptors(string):
    with pytest.raises(ValueError):
        HIDDescriptor.from_string(string)


def test_ids_or_path_required(fake_hidapi):
    with pytest.raises(AdapterConfigurationError):
        HID(0x04D8)


def test_missing_hidapi(monkeypatch):
    monkeypatch.setattr(hid_module, "_hidapi", None)
    with pytest.raises(ImportError, match="syndesi\\[hid\\]"):
        HID(0x04D8, 0x00DD)


# ┌─────────────┐
# │ Enumeration │
# └─────────────┘


def test_list_devices(fake_hidapi):
    fake_hidapi.plug(fake_hidapi.Hardware(0x04D8, 0x00DD, serial_number="A", product="MCP2221"))
    fake_hidapi.plug(fake_hidapi.Hardware(0x1234, 0x5678, interface=1))
    devices = HID.list_devices()
    assert [d.descriptor for d in devices] == ["hid:04d8:00dd:A@0", "hid:1234:5678@1"]
    assert devices[0].product == "MCP2221"
    assert "MCP2221" in str(devices[0])
    assert [d.descriptor for d in HID.list_devices(0x1234)] == ["hid:1234:5678@1"]


# ┌─────────┐
# │ Opening │
# └─────────┘


def test_open_by_ids(fake_hidapi):
    hardware = fake_hidapi.plug(fake_hidapi.Hardware(0x04D8, 0x00DD, on_write=echo))
    with HID(0x04D8, 0x00DD) as dev:
        assert dev.query(b"\x10\x20") == b"\x10\x20"
    assert hardware.opened == 1


def test_open_picks_serial_and_interface(fake_hidapi):
    fake_hidapi.plug(fake_hidapi.Hardware(0x04D8, 0x00DD, serial_number="A", on_write=echo))
    second = fake_hidapi.plug(
        fake_hidapi.Hardware(0x04D8, 0x00DD, serial_number="B", interface=2, on_write=echo)
    )
    with HID(0x04D8, 0x00DD, serial_number="B") as dev:
        dev.query(b"x")
    with HID(0x04D8, 0x00DD, interface=2) as dev:
        dev.query(b"y")
    assert second.opened == 2


def test_open_by_path(fake_hidapi):
    hardware = fake_hidapi.plug(fake_hidapi.Hardware(0x04D8, 0x00DD, on_write=echo))
    with HID(path=hardware.path) as dev:
        assert dev.query(b"\x01") == b"\x01"
        assert str(dev.descriptor) == f"hid:path={hardware.path}"


def test_open_missing_device(fake_hidapi):
    dev = HID(0x04D8, 0x00DD)
    with pytest.raises(AdapterOpenError, match="no such HID device"):
        dev.open()


# ┌──────────────────┐
# │ Reports, framing │
# └──────────────────┘


def test_report_id_and_padding(fake_hidapi):
    hardware = fake_hidapi.plug(fake_hidapi.Hardware(0x04D8, 0x00DD))
    with HID(0x04D8, 0x00DD, report_size=8) as dev:
        dev.write(b"\x10")
    with HID(0x04D8, 0x00DD, report_id=3) as dev:
        dev.write(b"\x10")
    with HID(0x04D8, 0x00DD, report_id=None) as dev:
        dev.write(b"\x05\x10")
    assert hardware.written == [
        b"\x00\x10" + bytes(7),
        b"\x03\x10",
        b"\x05\x10",
    ]


def test_report_too_long(fake_hidapi):
    fake_hidapi.plug(fake_hidapi.Hardware(0x04D8, 0x00DD))
    with HID(0x04D8, 0x00DD, report_size=4) as dev:
        with pytest.raises(AdapterWriteError, match="don't fit"):
            dev.write(b"12345")
        dev.write(b"1234")  # still open


def test_one_report_one_frame(fake_hidapi):
    """FragmentSC : two reports arriving together stay two frames"""
    hardware = fake_hidapi.plug(
        fake_hidapi.Hardware(0x04D8, 0x00DD, on_write=lambda r: [b"first", b"second"])
    )
    with HID(0x04D8, 0x00DD) as dev:
        assert dev.query(b"go") == b"first"
        assert dev.read() == b"second"
    assert hardware.written == [b"\x00go"]


def test_stop_conditions_can_be_changed(fake_hidapi):
    """A device streaming text over reports"""
    hardware = fake_hidapi.plug(
        fake_hidapi.Hardware(0x04D8, 0x00DD, on_write=lambda r: [b"21.", b"5\n"])
    )
    with HID(0x04D8, 0x00DD, stop_conditions=Termination(b"\n")) as dev:
        assert dev.query(b"T?") == b"21.5\n"
    assert hardware.written == [b"\x00T?"]


def test_unsolicited_report(fake_hidapi):
    hardware = fake_hidapi.plug(fake_hidapi.Hardware(0x04D8, 0x00DD))
    with HID(0x04D8, 0x00DD) as dev:
        dev.open()
        hardware.answer(b"\x01button")
        assert dev.read() == b"\x01button"


# ┌─────────────────┐
# │ Feature reports │
# └─────────────────┘


def test_feature_reports(fake_hidapi):
    hardware = fake_hidapi.plug(fake_hidapi.Hardware(0x04D8, 0x00DD))
    hardware.features[2] = b"\xaa\xbb\xcc"
    with HID(0x04D8, 0x00DD) as dev:
        dev.send_feature_report(b"\x01\x02", report_id=4)
        assert dev.get_feature_report(2, 3) == b"\xaa\xbb\xcc"
    assert hardware.sent_features == [b"\x04\x01\x02"]


def test_feature_report_opens_the_adapter(fake_hidapi):
    hardware = fake_hidapi.plug(fake_hidapi.Hardware(0x04D8, 0x00DD))
    dev = HID(0x04D8, 0x00DD)
    dev.send_feature_report(b"\x01")
    assert dev.is_open and hardware.opened == 1
    dev.close()


# ┌─────────────┐
# │ Disconnects │
# └─────────────┘


def test_unplug_closes_the_adapter(fake_hidapi):
    hardware = fake_hidapi.plug(fake_hidapi.Hardware(0x04D8, 0x00DD))
    dev = HID(0x04D8, 0x00DD)
    events = []
    dev.register_event_callback(events.append)
    dev.open()
    hardware.unplugged = True
    deadline = time.time() + 2
    while dev.is_open and time.time() < deadline:
        time.sleep(0.01)
    assert not dev.is_open
    assert any(isinstance(e, AdapterClosedEvent) for e in events)
    with pytest.raises((AdapterDisconnectedError, AdapterWriteError)):
        dev.write(b"x")


# ┌──────────────┐
# │ Auto, async  │
# └──────────────┘


def test_auto_adapter(fake_hidapi):
    fake_hidapi.plug(fake_hidapi.Hardware(0x04D8, 0x00DD, serial_number="S", on_write=echo))
    dev = auto_adapter("hid:04d8:00dd:S")
    assert isinstance(dev, HID)
    assert dev.query(b"auto") == b"auto"
    dev.close()
    assert isinstance(auto_async_adapter("hid:04d8:00dd"), AsyncHID)


def test_async(fake_hidapi):
    hardware = fake_hidapi.plug(fake_hidapi.Hardware(0x04D8, 0x00DD, on_write=echo))
    hardware.features[1] = b"\x07"

    async def main():
        async with AsyncHID(0x04D8, 0x00DD) as dev:
            answer = await dev.query(b"\x42")
            feature = await dev.get_feature_report(1, 1)
            await dev.send_feature_report(b"\x09", report_id=1)
        return answer, feature

    assert asyncio.run(main()) == (b"\x42", b"\x07")
    assert hardware.sent_features == [b"\x01\x09"]
