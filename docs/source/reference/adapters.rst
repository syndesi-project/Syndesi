Adapters
========

.. currentmodule:: syndesi

Adapters move bytes between your program and a device. Guides: :doc:`/how-to/connect`,
:doc:`/how-to/ip-server`.

Common methods
--------------

Every adapter has these methods. The async adapters have the same, as coroutines.

.. autoclass:: syndesi.adapters.adapter.Adapter
   :members: open, close, write, read, read_detailed, query, query_detailed,
             set_timeout, set_default_timeout, set_stop_conditions,
             set_default_stop_conditions, clear_read_buffer, is_open, descriptor,
             timeout, stop_conditions, register_event_callback, clear_event_callbacks
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.adapter.AsyncAdapter
   :no-members:
   :no-show-inheritance:

Transports
----------

.. autoclass:: syndesi.adapters.ip.IP
   :members: set_default_port
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.serialport.SerialPort
   :members: list_ports, set_default_baudrate, clear_read_buffer, flush
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.serialport.Parity
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.visa.Visa
   :members: list_devices
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.ipserver.IPServer
   :members: set_default_port
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.hid.HID
   :members: list_devices, send_feature_report, get_feature_report
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.hid.HIDDeviceInfo
   :members: descriptor
   :no-show-inheritance:
   :no-index:

Async variants
--------------

Same parameters and methods as their sync counterparts, see :doc:`/how-to/async`.

.. autoclass:: syndesi.adapters.ip.AsyncIP
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.serialport.AsyncSerialPort
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.visa.AsyncVisa
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.ipserver.AsyncIPServer
   :no-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.hid.AsyncHID
   :no-members:
   :no-show-inheritance:

From a string
-------------

.. autofunction:: syndesi.adapters.auto.auto_adapter

.. autofunction:: syndesi.adapters.auto.auto_async_adapter

Accepted strings:

======================================  ============================
``"tcp:192.168.1.10:5025"``             ``IP``, TCP
``"udp:192.168.1.50:9000"``             ``IP``, UDP
``"serial:/dev/ttyUSB0:115200"``        ``SerialPort``
``"serial:COM3:9600"``                  ``SerialPort``
``"i2c:/dev/i2c-1@0x48"``               ``I2C``, native bus (Linux)
``"spi:/dev/spidev0.1"``                ``SPI``, native bus (Linux)
``"hid:04d8:00dd"``                     ``HID``, ``hid:VID:PID[:SERIAL][@IFACE]``
``"GPIB0::14::INSTR"`` (any VISA name)  ``Visa``, if pyvisa is installed
======================================  ============================

Frames and read scope
---------------------

.. autoclass:: syndesi.adapters.framer.AdapterReadFrame
   :members:
   :undoc-members:
   :no-show-inheritance:

.. autoclass:: syndesi.adapters.engine.ReadScope
   :members:
   :undoc-members:
   :no-show-inheritance:
