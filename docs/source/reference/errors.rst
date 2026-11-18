Errors
======

``from syndesi.tools.errors import ...``. Guide: :doc:`/how-to/errors`.

.. code-block:: text

   SyndesiError
   ├── AdapterError
   │   ├── AdapterOpenError
   │   ├── AdapterWriteError
   │   ├── AdapterDisconnectedError
   │   ├── AdapterConfigurationError
   │   └── AdapterReadError
   │       └── AdapterTimeoutError
   ├── ProtocolError
   │   ├── ProtocolWriteError
   │   └── ProtocolReadError
   └── ModbusError                    (syndesi.protocols.modbus)
       └── ModbusException

.. autoexception:: syndesi.tools.errors.SyndesiError
   :no-show-inheritance:

Adapter errors
--------------

.. autoexception:: syndesi.tools.errors.AdapterError
.. autoexception:: syndesi.tools.errors.AdapterOpenError
.. autoexception:: syndesi.tools.errors.AdapterWriteError
.. autoexception:: syndesi.tools.errors.AdapterDisconnectedError
.. autoexception:: syndesi.tools.errors.AdapterConfigurationError
.. autoexception:: syndesi.tools.errors.AdapterReadError
.. autoexception:: syndesi.tools.errors.AdapterTimeoutError

Protocol errors
---------------

.. autoexception:: syndesi.tools.errors.ProtocolError
.. autoexception:: syndesi.tools.errors.ProtocolWriteError
.. autoexception:: syndesi.tools.errors.ProtocolReadError

Modbus errors
-------------

.. autoexception:: syndesi.protocols.modbus.ModbusError
   :no-index:

See :class:`~syndesi.protocols.modbus.ModbusException`.
