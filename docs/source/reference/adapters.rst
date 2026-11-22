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
