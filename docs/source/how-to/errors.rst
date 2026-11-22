Handle errors and timeouts
==========================

Every Syndesi error derives from ``SyndesiError``, in ``syndesi.tools.errors``.

The device doesn't answer
-------------------------

.. code-block:: python

   from syndesi.tools.errors import AdapterTimeoutError

   try:
       dev.query(b"MEAS?\n")
   except AdapterTimeoutError as e:
       print(f"No answer within {e.timeout} s")

If the device is just slow, raise the adapter's timeout:
``IP("192.168.1.10", 5025, timeout=10)``.

The device can't be reached
---------------------------

.. code-block:: python

   from syndesi.tools.errors import AdapterOpenError

   dev = IP("192.168.1.10", 5025)
   try:
       dev.open()
   except AdapterOpenError as e:
       print(e)   # Failed to open adapter tcp:192.168.1.10:5025 ([Errno 111] Connection refused)

The device went away
--------------------

.. code-block:: python

   from syndesi.tools.errors import AdapterDisconnectedError

   try:
       dev.read()
   except AdapterDisconnectedError:
       dev.open()   # try again

Catch everything from one device
--------------------------------

.. code-block:: python

   from syndesi.tools.errors import AdapterError, ProtocolError

   try:
       psu.set_voltage(12)
   except (AdapterError, ProtocolError) as e:
       log.error("Power supply: %s", e)

Modbus refusals
---------------

.. code-block:: python

   from syndesi.protocols.modbus import ModbusException

   try:
       plc.write_single_register(9999, 1)
   except ModbusException as e:
       print(e.exception_code)   # ExceptionCode.ILLEGAL_DATA_ADDRESS

The error tree
--------------

.. code-block:: text

   SyndesiError
   ├── AdapterError
   │   ├── AdapterOpenError            couldn't open (refused, port busy, no such device)
   │   ├── AdapterWriteError           couldn't write
   │   ├── AdapterDisconnectedError    the device closed the connection
   │   ├── AdapterConfigurationError   invalid settings
   │   └── AdapterReadError
   │       └── AdapterTimeoutError     no answer in time
   ├── ProtocolError
   │   ├── ProtocolWriteError          couldn't encode a payload
   │   └── ProtocolReadError           couldn't decode an answer
   └── ModbusError
       └── ModbusException             the Modbus device answered with an exception

Invalid arguments (a negative length, an I2C address above ``0x7F``…) raise the usual
``ValueError``.
