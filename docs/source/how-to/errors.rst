Handle errors and timeouts
==========================

Every Syndesi error derives from ``SyndesiError``, in ``syndesi.errors``. Messages say
what went wrong and what to check: print the error, it is often enough.

Errors are raised, not printed: if you catch one, nothing appears in the console. To
see what happened anyway, :ref:`turn on logging <debug-logging>`.

The device doesn't answer
-------------------------

.. code-block:: python

   from syndesi.errors import AdapterTimeoutError

   try:
       dev.query(b"MEAS?\n")
   except AdapterTimeoutError as e:
       print(f"No answer within {e.timeout} s")
       if e.received is not None:
           print(f"Received {e.received!r}, but not a complete frame")

If the device is just slow, raise the timeout of the layer you talk to:
``IP("192.168.1.10", 5025, timeout=10)``, or ``SCPI(IP(...), timeout=10)`` with a
protocol. See :ref:`timeouts`.

If ``e.received`` holds data, the device did answer, but the frame never completed:
most often a wrong terminator (``\r\n`` instead of ``\n``, ...).

The device can't be reached
---------------------------

.. code-block:: python

   from syndesi.errors import AdapterOpenError

   dev = IP("192.168.1.10", 5025)
   try:
       dev.open()
   except AdapterOpenError as e:
       print(e)

.. code-block:: text

   Failed to open adapter tcp:192.168.1.10:5025 : connection refused. Nothing listens on
   192.168.1.10:5025 : check the port, and that the device (or its server) is running

Permission denied
-----------------

On Linux, serial ports and buses (``/dev/ttyUSB0``, ``/dev/i2c-1``, ``/dev/spidev0.0``)
belong to a group, and only its members may open them. The error says which one, and
the command to join it:

.. code-block:: text

   AdapterOpenError: Cannot open /dev/ttyUSB0 : permission denied
   /dev/ttyUSB0 belongs to the group 'dialout'. Add your user to it, then log out and
   back in :
       sudo usermod -aG dialout $USER

Logging out and back in matters: a group is only applied to new sessions. Check with
``groups`` that it is listed.

If the file belongs to root alone, the error gives a udev rule that assigns it a group.
On Windows, "access denied" on a COM port means another program has it open (a serial
monitor, a terminal…): close it.

Text where bytes are expected
-----------------------------

An adapter sends ``bytes``, a text protocol (``Delimited``, ``SCPI``) sends ``str``.
Mixing them up raises an error saying what to write instead:

.. code-block:: text

   TypeError: IP.write() sends bytes, not str : write b'hello\n', or wrap the adapter
   in a protocol to exchange text, Delimited(IP(...))

The device went away
--------------------

.. code-block:: python

   from syndesi.errors import AdapterDisconnectedError

   try:
       dev.read()
   except AdapterDisconnectedError:
       dev.open()   # try again

Catch everything from one device
--------------------------------

.. code-block:: python

   from syndesi.errors import AdapterError, ProtocolError

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
