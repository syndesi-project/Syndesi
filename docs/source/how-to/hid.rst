Talk to a HID device
====================

Many USB gadgets are **HID** devices: USB to I2C/GPIO converters (MCP2221, CP2112),
relay boards, data loggers, custom firmwares… They need no driver: the operating system
already knows them. ``HID`` reads and writes their raw *reports*.

Install
-------

``HID`` uses `hidapi <https://pypi.org/project/hidapi/>`_, an optional dependency:

.. code-block:: console

   $ pip install "syndesi[hid]"

.. tip::

   On Linux, a regular user needs read/write access to ``/dev/hidraw*``. A udev rule
   does it, for an MCP2221 for instance:

   .. code-block:: text
      :caption: /etc/udev/rules.d/99-mcp2221.rules

      SUBSYSTEM=="hidraw", ATTRS{idVendor}=="04d8", ATTRS{idProduct}=="00dd", MODE="0666"

Find your device
----------------

.. code-block:: python

   >>> from syndesi import HID
   >>> for device in HID.list_devices():
   ...     print(device)
   hid:04d8:00dd@2  Microchip Technology Inc. MCP2221 USB-I2C/UART Combo

Or from the command line: ``syndesi term hid --list``.

Open it
-------

By vendor and product id:

.. code-block:: python

   from syndesi import HID

   dev = HID(0x04D8, 0x00DD)

When several identical devices are connected, or one device has several HID
interfaces:

.. code-block:: python

   HID(0x04D8, 0x00DD, serial_number="0001234567")
   HID(0x1234, 0x5678, interface=1)
   HID(path=device.path)            # a path given by list_devices()

Exchange reports
----------------

A ``write`` sends one output report, a ``read`` returns one input report:

.. code-block:: python

   dev.write(b"\x10")
   status = dev.read()             # 64 bytes, the report that came back
   status = dev.query(b"\x10")     # the same, in one call

Each report is a frame of its own (``FragmentSC``), even when several arrive together.

Report ids
----------

hidapi expects each output report to start with its *report id*. Syndesi adds it:

==============================  ==================================================
``HID(..., report_id=0)``       default, for devices without numbered reports
``HID(..., report_id=5)``       every report is sent as report 5
``HID(..., report_id=None)``    sent as is: write the id yourself, first byte
==============================  ==================================================

Input reports are returned as hidapi gives them: numbered ones start with their id,
unnumbered ones don't.

Full-size reports
-----------------

Some devices, and Windows for all of them, only accept reports at their exact size.
``report_size`` pads every write with zeros:

.. code-block:: python

   dev = HID(0x04D8, 0x00DD, report_size=64)
   dev.write(b"\x10")              # sent as 0x00 + 0x10 + 63 zeros

Feature reports
---------------

.. code-block:: python

   dev.send_feature_report(b"\x01\x02", report_id=3)
   dev.get_feature_report(report_id=3, length=8)   # content, without the id

Async
-----

.. code-block:: python

   from syndesi import AsyncHID

   async with AsyncHID(0x04D8, 0x00DD) as dev:
       status = await dev.query(b"\x10")

Try it by hand
--------------

.. code-block:: console

   $ syndesi term hid 04d8:00dd --report-size 64
   ❯ 10
   10 00 00 00 ...

Lines are hex bytes, each one sent as a report. See :doc:`terminal`.

.. seealso::

   :doc:`bridges` uses an MCP2221 to reach I2C devices and drive GPIOs.
