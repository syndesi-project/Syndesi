Errors
======

``from syndesi.errors import ...``. Guide: :doc:`/how-to/errors`.

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

.. autoexception:: syndesi.errors.SyndesiError
   :no-show-inheritance:

Adapter errors
--------------

.. autoexception:: syndesi.errors.AdapterError
.. autoexception:: syndesi.errors.AdapterOpenError
.. autoexception:: syndesi.errors.AdapterWriteError
.. autoexception:: syndesi.errors.AdapterDisconnectedError
.. autoexception:: syndesi.errors.AdapterConfigurationError
.. autoexception:: syndesi.errors.AdapterReadError
.. autoexception:: syndesi.errors.AdapterTimeoutError

Protocol errors
---------------

.. autoexception:: syndesi.errors.ProtocolError
.. autoexception:: syndesi.errors.ProtocolWriteError
.. autoexception:: syndesi.errors.ProtocolReadError

Modbus errors
-------------

.. autoexception:: syndesi.protocols.modbus.ModbusError
   :no-index:

See :class:`~syndesi.protocols.modbus.ModbusException`.
