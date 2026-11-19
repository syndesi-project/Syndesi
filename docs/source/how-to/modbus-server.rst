Simulate a Modbus device
========================

``ModbusServer`` answers Modbus requests (it is a *slave*). Use it to simulate a PLC
while its real counterpart isn't there, to test a client, or to expose data from a
Python program to a SCADA system.

Start a server
--------------

.. tab-set::

   .. tab-item:: Modbus TCP

      .. code-block:: python

         from syndesi import IPServer, ModbusServer

         server = ModbusServer(IPServer("0.0.0.0"))   # port 502 by default
         server.serve_forever()

      Each client is served by its own thread.

   .. tab-item:: Modbus RTU

      .. code-block:: python

         from syndesi import ModbusServer, SerialPort

         server = ModbusServer(SerialPort("/dev/ttyUSB0", 19200), slave_address=1)
         server.serve_forever()

   .. tab-item:: Modbus ASCII

      .. code-block:: python

         from syndesi import ModbusServer, SerialPort

         server = ModbusServer(
             SerialPort("/dev/ttyUSB0", 9600, bytesize=7),
             serial_type="ASCII",
             slave_address=1,
         )
         server.serve_forever()

``serve_forever()`` blocks. Run it in a thread to keep working meanwhile, and call
``server.stop()`` to end it:

.. code-block:: python

   import threading

   threading.Thread(target=server.serve_forever, daemon=True).start()

Fill the data tables
--------------------

Tables are dictionaries, by address (starting at 1). Unset addresses read as ``0`` or
``False``:

.. code-block:: python

   server.holding_registers[1] = 1234
   server.input_registers[100] = 42
   server.coils[3] = True
   server.discrete_inputs[1] = True

Clients writing to the server change these tables, so you can also read them:
``server.holding_registers[10]`` is the last value a client wrote there.

Store a float or a string
-------------------------

.. code-block:: python

   from syndesi import ModbusMultiRegisterValue as Value

   for i, register in enumerate(Value.from_float(21.5, 2).to_registers()):
       server.holding_registers[10 + i] = register

Compute answers on the fly
--------------------------

Replace the answer to one kind of request with your own *handler*. It receives the
request and returns the response:

.. code-block:: python

   from syndesi.protocols.modbus import (
       ReadInputRegistersRequestSDU,
       ReadInputRegistersResponseSDU,
   )

   def read_inputs(request: ReadInputRegistersRequestSDU):
       values = [sensor.read(address) for address in
                 range(request.start_address, request.start_address + request.n_registers)]
       return ReadInputRegistersResponseSDU(values)

   server.set_handler(ReadInputRegistersRequestSDU, read_inputs)

Return ``server.default_handler(request)`` to keep the default behaviour, for instance
after validating a write. ``set_handler(RequestType, None)`` restores it.

Refuse a request
----------------

Raise ``ModbusException`` from a handler, the client receives the exception code:

.. code-block:: python

   from syndesi.protocols.modbus import (
       ExceptionCode,
       ModbusException,
       WriteSingleRegisterRequestSDU,
   )

   def write_register(request: WriteSingleRegisterRequestSDU):
       if not 0 <= request.value <= 1000:
           raise ModbusException(ExceptionCode.ILLEGAL_DATA_VALUE)
       return server.default_handler(request)

   server.set_handler(WriteSingleRegisterRequestSDU, write_register)

Device identity and diagnostics
-------------------------------

The server answers identification and diagnostics requests from these attributes:

.. code-block:: python

   server.server_id = b"PUMP-07"
   server.run_indicator_status = True
   server.exception_status = 0
   server.fifos[1] = [10, 20, 30]
   server.files[1][0] = 0xBEEF      # file 1, record 0

Diagnostics counters (``server.counters``) are kept up to date automatically.

Follow what happens
-------------------

.. code-block:: python

   from syndesi.protocols.modbus.server import ModbusRequestHandledEvent

   def on_event(event):
       if isinstance(event, ModbusRequestHandledEvent):
           print(event)

   server.register_event_callback(on_event)

Async
-----

``AsyncModbusServer`` takes an ``AsyncIPServer`` or ``AsyncSerialPort``, and its handlers
can be coroutines:

.. code-block:: python

   from syndesi import AsyncIPServer, AsyncModbusServer

   server = AsyncModbusServer(AsyncIPServer("0.0.0.0", 5020))
   await server.serve_forever()
