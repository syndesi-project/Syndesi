Read and write a Modbus device
==============================

``Modbus`` is a Modbus client (master). The adapter decides the flavour: ``IP`` gives
Modbus TCP, ``SerialPort`` gives Modbus RTU or ASCII. The methods are the same.

Connect
-------

.. tab-set::

   .. tab-item:: Modbus TCP

      .. code-block:: python

         from syndesi import IP, Modbus

         plc = Modbus(IP("192.168.1.100"))   # port 502 by default

   .. tab-item:: Modbus RTU

      .. code-block:: python

         from syndesi import Modbus, Parity, SerialPort

         meter = Modbus(
             SerialPort("/dev/ttyUSB0", 19200, parity=Parity.EVEN),
             slave_address=1,
         )

   .. tab-item:: Modbus ASCII

      .. code-block:: python

         from syndesi import Modbus, SerialPort

         drive = Modbus(
             SerialPort("COM3", 9600, bytesize=7),
             serial_type="ASCII",
             slave_address=17,
         )

Addresses start at **1**, like in most device manuals (register ``1`` is sent as ``0``
on the wire).

Registers
---------

.. code-block:: python

   plc.read_holding_registers(1, 4)          # [12, 0, 450, 7]
   plc.read_input_registers(100, 2)          # read-only registers
   plc.read_single_register(1)               # 12

   plc.write_single_register(1, 500)
   plc.write_multiple_registers(10, [1, 2, 3])

   plc.mask_write_register(1, and_mask=0xFF00, or_mask=0x0012)
   plc.read_write_multiple_registers(1, 2, 10, [7, 8])  # write then read, one request

Coils and discrete inputs
-------------------------

.. code-block:: python

   plc.read_coils(1, 8)                      # [True, False, ...]
   plc.read_single_coil(3)                   # True
   plc.read_discrete_inputs(1, 4)

   plc.write_single_coil(3, False)
   plc.write_multiple_coils(1, [True, True, False])

Floats, 32/64-bit integers and strings
--------------------------------------

Values wider than 16 bits span several registers. ``ModbusMultiRegisterValue`` converts
them:

.. code-block:: python

   from syndesi import ModbusMultiRegisterValue as Value

   # Read
   plc.read_multi_register_value(10, 2).to_float()      # 21.5      (32-bit float)
   plc.read_multi_register_value(12, 4).to_float()      # 64-bit double
   plc.read_multi_register_value(20, 2).to_int()        # -12       (signed 32-bit)
   plc.read_multi_register_value(22, 2).to_uint()       # unsigned 32-bit
   plc.read_multi_register_value(30, 8).to_string()     # 'PUMP-07'

   # Write
   plc.write_multi_register_value(10, Value.from_float(21.5, 2))
   plc.write_multi_register_value(20, Value.from_int(-12, 2))
   plc.write_multi_register_value(30, Value.from_string("PUMP-07", 8))

Byte and word order
-------------------

Devices disagree on the order of the registers of a value. If the numbers look wrong,
try another order:

.. code-block:: python

   plc.read_multi_register_value(10, 2, word_order="little").to_float()

=================  =================  ===================================
``byte_order``     ``word_order``     ``0x12345678`` is sent as
=================  =================  ===================================
``big``            ``big``            ``12 34 56 78`` (default, ABCD)
``little``         ``big``            ``34 12 78 56`` (BADC)
``big``            ``little``         ``56 78 12 34`` (CDAB)
``little``         ``little``         ``78 56 34 12`` (DCBA)
=================  =================  ===================================

Device information and diagnostics
----------------------------------

.. code-block:: python

   plc.report_server_id(server_id_length=7, additional_data_length=0)
   plc.read_exception_status()
   plc.get_comm_event_counter()
   plc.diagnostics_return_query_data()            # loopback test, True if OK
   plc.diagnostics_return_bus_message_count()
   plc.read_fifo_queue(1)
   plc.read_file_record([(1, 0, 4)])              # (file, record, length)

See :doc:`/reference/modbus` for the complete list.

Handle refusals
---------------

When a device refuses a request, it answers with an exception code, raised as
``ModbusException``:

.. code-block:: python

   from syndesi.protocols.modbus import ExceptionCode, ModbusException

   try:
       plc.write_single_register(9999, 1)
   except ModbusException as e:
       if e.exception_code == ExceptionCode.ILLEGAL_DATA_ADDRESS:
           print("No such register")

Async
-----

``AsyncModbus`` has the same methods, as coroutines:

.. code-block:: python

   from syndesi import AsyncIP, AsyncModbus

   plc = AsyncModbus(AsyncIP("192.168.1.100"))
   values = await plc.read_holding_registers(1, 4)
