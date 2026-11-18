A Modbus device in five minutes
===============================

**Modbus** is the language of industrial equipment: PLCs, energy meters, motor drives,
temperature controllers. In this tutorial you will create a Modbus TCP device with
Syndesi, then talk to it as a client, the way you would talk to a real PLC.

.. rubric:: What you need

Syndesi installed and two terminals.

Create the device
-----------------

A Modbus device stores its data in four tables: **coils** (on/off outputs),
**discrete inputs** (on/off inputs), **holding registers** (16-bit values you can write)
and **input registers** (16-bit values you can only read).

``ModbusServer`` gives you all four, ready to fill. Save this as ``device.py``:

.. code-block:: python
   :caption: device.py

   from syndesi import IPServer, ModbusServer

   device = ModbusServer(IPServer("127.0.0.1", 5020))

   device.holding_registers[1] = 1234   # a setpoint
   device.holding_registers[2] = 42
   device.coils[3] = True               # a relay, switched on

   print("Modbus device on 127.0.0.1:5020")
   device.serve_forever()

Run it in the first terminal:

.. code-block:: console

   $ python device.py
   Modbus device on 127.0.0.1:5020

.. note::

   The standard Modbus port is 502, but ports below 1024 need administrator rights on
   most systems. We use 5020 for this tutorial.

Read registers
--------------

In the second terminal:

.. code-block:: python

   >>> from syndesi import IP, Modbus
   >>> plc = Modbus(IP("127.0.0.1", 5020))
   >>> plc.read_holding_registers(1, 2)
   [1234, 42]

``read_holding_registers(start_address, n_registers)`` returns a list of integers.
Addresses start at 1, as in most device manuals.

Write registers
---------------

.. code-block:: python

   >>> plc.write_single_register(2, 500)
   >>> plc.read_single_register(2)
   500
   >>> plc.write_multiple_registers(5, [10, 20, 30])
   >>> plc.read_holding_registers(5, 3)
   [10, 20, 30]

Switch coils
------------

.. code-block:: python

   >>> plc.read_coils(1, 4)
   [False, False, True, False]
   >>> plc.write_single_coil(1, True)
   >>> plc.read_single_coil(1)
   True

Values larger than a register
-----------------------------

A register holds 16 bits. A temperature like ``21.5`` is a 32-bit float, so it takes two
registers. ``ModbusMultiRegisterValue`` does the conversion in both directions:

.. code-block:: python

   >>> from syndesi import ModbusMultiRegisterValue
   >>> value = ModbusMultiRegisterValue.from_float(21.5, n_registers=2)
   >>> plc.write_multi_register_value(10, value)
   >>> plc.read_holding_registers(10, 2)
   [16812, 0]
   >>> plc.read_multi_register_value(10, 2).to_float()
   21.5

The same works with ``from_int``, ``from_uint`` and ``from_string``. When a device
stores the two halves the other way round, pass ``word_order="little"``.

When the device says no
-----------------------

Devices refuse some requests: an address that doesn't exist, a value out of range… They
answer with a Modbus *exception*, which Syndesi raises as ``ModbusException``. Let's
make our device refuse something. Stop it with :kbd:`Ctrl+C` and add a custom
**handler** to ``device.py``:

.. code-block:: python
   :caption: device.py

   from syndesi import IPServer, ModbusServer
   from syndesi.protocols.modbus import (
       ExceptionCode,
       ModbusException,
       WriteSingleRegisterRequestSDU,
   )

   device = ModbusServer(IPServer("127.0.0.1", 5020))
   device.holding_registers[1] = 1234


   def write_register(request: WriteSingleRegisterRequestSDU):
       if request.value > 1000:
           raise ModbusException(ExceptionCode.ILLEGAL_DATA_VALUE)
       return device.default_handler(request)


   device.set_handler(WriteSingleRegisterRequestSDU, write_register)

   print("Modbus device on 127.0.0.1:5020")
   device.serve_forever()

Restart it, then on the client side:

.. code-block:: python

   >>> plc = Modbus(IP("127.0.0.1", 5020))
   >>> plc.write_single_register(1, 800)
   >>> plc.write_single_register(1, 5000)
   Traceback (most recent call last):
     ...
   syndesi.protocols.modbus.common.ModbusException: 03 : Invalid data value

What you learned
----------------

- ``ModbusServer`` turns any Python script into a Modbus device, with its four data
  tables.
- ``Modbus`` is the client: ``read_holding_registers``, ``write_single_coil``…
- ``ModbusMultiRegisterValue`` handles floats, 32-bit integers and strings.
- Refusals from a device arrive as ``ModbusException``.

The client works the same over a serial line (Modbus RTU), see
:doc:`/how-to/modbus-client`.

.. container:: sd-text-right

   :doc:`Where next? The how-to guides → </how-to/index>`
